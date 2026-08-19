"""
Cosechador de proxies geo-dirigido (LATAM-first)
================================================
Dos mejoras sobre el ProxyFetcher base:

  1) FUENTES GEO-DIRIGIDAS: muchas APIs aceptan ?country=PE y devuelven
     directo proxies peruanas / EC / CO / BO / CL. El fetcher base solo
     baja listas globales (=> casi nada de LATAM). Aquí pedimos por país.

  2) DESCARGA VÍA NUESTRAS PROXIES: algunas fuentes limitan por IP o
     geo-bloquean. Si pasamos `via_proxies` (proxies vivas del baúl),
     rotamos la IP de salida por fuente para esquivar rate-limits y
     cosechar más. Si la proxy falla, cae a descarga directa.

Devuelve un dict {address -> ProxyProtocol} listo para inyectar en el
motor de verificación (engine.ProxyChecker). NO verifica vida: solo cosecha.
"""

import re
import json
import random
import asyncio
from pathlib import Path
import sys

import aiohttp

# Motor (raíz del repo) — para ProxyProtocol / validación de IP / config.
ENGINE_DIR = Path(__file__).resolve().parent.parent.parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))
import proxy_checker_v2 as engine  # noqa: E402

P = engine.ProxyProtocol

# Países objetivo prioritarios (Perú primero, luego vecinos cercanos).
# Coincide con SA_PROXIMITY_ORDER del anti-ban para que el harvest alimente
# justo lo que el anti-ban necesita.
LATAM_COUNTRIES = ["PE", "EC", "CO", "BO", "CL", "BR", "AR", "MX", "VE", "PY", "UY"]

TIMEOUT = getattr(engine.Config, "TIMEOUT_FETCH", 20)
UAS = getattr(engine.Config, "USER_AGENTS", ["Mozilla/5.0"])


# ──────────────────────────────────────────────────────────────
#  CONSTRUCTORES DE FUENTES POR PAÍS
# ──────────────────────────────────────────────────────────────
def _country_sources(cc: str):
    """
    Devuelve [(nombre, url, protocolo_default, parser)] geo-dirigidos a `cc`.
    parser: 'text' (ip:port plano) | 'geonode' (JSON) | 'prefixed' (proto://ip:port)
    """
    cc = cc.upper()
    out = []
    # ProxyScrape v4 — soporta country + protocolo. Devuelve proto://ip:port.
    for proto in ("http", "socks4", "socks5"):
        out.append((
            f"ProxyScrape {proto} {cc}",
            f"https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies"
            f"&protocol={proto}&country={cc}&proxy_format=protocolipport&format=text",
            P(proto), "prefixed",
        ))
    # GeoNode — JSON con país y protocolos por proxy. Paginado (más páginas = más proxies).
    for page in (1, 2):
        out.append((
            f"GeoNode {cc} p{page}",
            f"https://proxylist.geonode.com/api/proxy-list?limit=500&page={page}"
            f"&sort_by=lastChecked&sort_type=desc&country={cc}",
            P.HTTP, "geonode",
        ))
    # proxy-list.download — country param, por protocolo, ip:port plano.
    for proto in ("http", "https", "socks4", "socks5"):
        out.append((
            f"ProxyListDownload {proto} {cc}",
            f"https://www.proxy-list.download/api/v1/get?type={proto}&country={cc}",
            P(proto), "text",
        ))
    return out


# Agregadores globales extra (no presentes en engine.SOURCES) — alto rendimiento.
# Se cosechan completos y luego el motor detecta el país real de cada proxy.
EXTRA_GLOBAL = [
    ("GeoNode global p1",
     "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc",
     P.HTTP, "geonode"),
    ("GeoNode global p2",
     "https://proxylist.geonode.com/api/proxy-list?limit=500&page=2&sort_by=lastChecked&sort_type=desc",
     P.HTTP, "geonode"),
    ("GeoNode global p3",
     "https://proxylist.geonode.com/api/proxy-list?limit=500&page=3&sort_by=lastChecked&sort_type=desc",
     P.HTTP, "geonode"),
    ("ProxyListDownload http",
     "https://www.proxy-list.download/api/v1/get?type=http", P.HTTP, "text"),
    ("ProxyListDownload https",
     "https://www.proxy-list.download/api/v1/get?type=https", P.HTTPS, "text"),
    ("ProxyListDownload socks4",
     "https://www.proxy-list.download/api/v1/get?type=socks4", P.SOCKS4, "text"),
    ("ProxyListDownload socks5",
     "https://www.proxy-list.download/api/v1/get?type=socks5", P.SOCKS5, "text"),
    ("ProxyScrape v4 all",
     "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text",
     P.HTTP, "prefixed"),
    ("Vakhov http",
     "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt", P.HTTP, "text"),
    ("Vakhov https",
     "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt", P.HTTPS, "text"),
    ("Vakhov socks4",
     "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt", P.SOCKS4, "text"),
    ("Vakhov socks5",
     "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt", P.SOCKS5, "text"),
    ("proxifly http",
     "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
     P.HTTP, "prefixed"),
    ("proxifly socks4",
     "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt",
     P.SOCKS4, "prefixed"),
    ("proxifly socks5",
     "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
     P.SOCKS5, "prefixed"),
    ("Zaeem20 http",
     "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt", P.HTTP, "text"),
    ("Zaeem20 socks5",
     "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt", P.SOCKS5, "text"),
    # ── Ronda 2 (2026-06-26): repos extra de alto rendimiento ──
    ("hookzof socks5",
     "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", P.SOCKS5, "text"),
    ("zloi hideip http",  # formato ip:port:country -> el regex saca ip:port
     "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt", P.HTTP, "text"),
    ("zloi hideip https",
     "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt", P.HTTPS, "text"),
    ("zloi hideip socks4",
     "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks4.txt", P.SOCKS4, "text"),
    ("zloi hideip socks5",
     "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks5.txt", P.SOCKS5, "text"),
    ("MuRongPIG http",
     "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt", P.HTTP, "text"),
    ("MuRongPIG socks4",
     "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks4.txt", P.SOCKS4, "text"),
    ("MuRongPIG socks5",
     "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt", P.SOCKS5, "text"),
    ("yemixzy http",
     "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/http.txt", P.HTTP, "text"),
    ("yemixzy socks5",
     "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks5.txt", P.SOCKS5, "text"),
    ("TuanMinPay all",
     "https://raw.githubusercontent.com/TuanMinPay/live-proxy/master/all.txt", P.HTTP, "prefixed"),
    ("KangProxy http",
     "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt", P.HTTP, "text"),
    ("KangProxy https",
     "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/https/https.txt", P.HTTPS, "text"),
    ("KangProxy socks5",
     "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt", P.SOCKS5, "text"),
    ("elliottophellia http",
     "https://raw.githubusercontent.com/elliottophellia/proxylist/master/results/http/global/http_checked.txt",
     P.HTTP, "text"),
    ("elliottophellia socks5",
     "https://raw.githubusercontent.com/elliottophellia/proxylist/master/results/socks5/global/socks5_checked.txt",
     P.SOCKS5, "text"),
    ("databay http",
     "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/http.txt", P.HTTP, "text"),
    ("databay socks5",
     "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/socks5.txt", P.SOCKS5, "text"),
    ("proxyscrape socks5 v2",
     "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country=all",
     P.SOCKS5, "text"),
]


# ──────────────────────────────────────────────────────────────
#  PARSERS
# ──────────────────────────────────────────────────────────────
def _parse_text(text, default_proto):
    out = []
    for addr in engine.ProxyFetcher._parse_ip_port(text):
        out.append((addr, default_proto))
    return out


def _parse_prefixed(text, default_proto):
    out = engine.ProxyFetcher._parse_protocol_prefixed(text)
    if out:
        return out
    return _parse_text(text, default_proto)  # fallback si no traía prefijo


def _parse_geonode(text, default_proto):
    out = []
    try:
        data = json.loads(text)
    except Exception:
        return _parse_text(text, default_proto)
    for item in data.get("data", []):
        ip = str(item.get("ip", "")).strip()
        port = str(item.get("port", "")).strip()
        if not engine._valid_ip(ip) or not port.isdigit():
            continue
        protos = item.get("protocols") or []
        proto = default_proto
        if protos:
            try:
                proto = P(str(protos[0]).lower())
            except Exception:
                proto = default_proto
        out.append((f"{ip}:{port}", proto))
    return out


_PARSERS = {"text": _parse_text, "prefixed": _parse_prefixed, "geonode": _parse_geonode}


# ──────────────────────────────────────────────────────────────
#  DESCARGA (con rotación opcional por nuestras proxies)
# ──────────────────────────────────────────────────────────────
async def _fetch_one(session, name, url, proto, kind, via=None):
    """Descarga una fuente. `via` = 'http://ip:port' opcional (exit node)."""
    headers = {"User-Agent": random.choice(UAS)}
    for attempt in (via, None) if via else (None,):
        try:
            async with session.get(
                url, headers=headers, proxy=attempt,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    continue
                text = await resp.text()
            parsed = _PARSERS.get(kind, _parse_text)(text, proto)
            if parsed:
                return name, parsed, (attempt or "directo")
        except Exception:
            continue
    return name, [], "fallo"


def _pick_exit_nodes(via_proxies, k=12):
    """Selecciona hasta k proxies http/https vivas como nodos de salida."""
    if not via_proxies:
        return []
    usable = []
    for r in via_proxies:
        proto = (r.get("protocol") or "").lower()
        addr = r.get("address")
        if addr and proto in ("http", "https"):
            usable.append(f"http://{addr}")
    random.shuffle(usable)
    return usable[:k]


# Fuentes que PRE-VALIDAN o geo-dirigen (alta tasa de vivas) → verificar primero.
# Los repos github masivos traen mucho volumen pero mayormente muerto: relleno.
def _is_priority(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in ("geonode", "proxyscrape", "proxifly", "proxylistdownload"))


async def harvest(via_proxies=None, countries=None, include_global=True):
    """
    Cosecha proxies. Devuelve (proxies_dict, report, priority_set).
      via_proxies : filas del baúl para rutear la descarga (opcional)
      countries   : lista ISO-2 a geo-dirigir (default LATAM_COUNTRIES)
      include_global: además baja agregadores globales extra
      priority_set: addresses de fuentes pre-validadas/geo (verificar primero)
    """
    countries = countries or LATAM_COUNTRIES
    sources = []
    for cc in countries:
        sources.extend(_country_sources(cc))
    if include_global:
        sources.extend(EXTRA_GLOBAL)

    exit_nodes = _pick_exit_nodes(via_proxies)

    proxies = {}
    priority = set()
    report = {"sources": 0, "ok": 0, "raw": 0, "unique": 0, "priority": 0,
              "via_proxy": bool(exit_nodes), "per_source": {}}

    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, (name, url, proto, kind) in enumerate(sources):
            via = exit_nodes[i % len(exit_nodes)] if exit_nodes else None
            tasks.append(_fetch_one(session, name, url, proto, kind, via))
        results = await asyncio.gather(*tasks, return_exceptions=True)

    report["sources"] = len(sources)
    for res in results:
        if isinstance(res, Exception):
            continue
        name, parsed, _route = res
        if parsed:
            report["ok"] += 1
        report["raw"] += len(parsed)
        report["per_source"][name] = len(parsed)
        prio = _is_priority(name)
        for addr, proto in parsed:
            if addr not in proxies:
                proxies[addr] = proto
            if prio:
                priority.add(addr)
    report["unique"] = len(proxies)
    report["priority"] = len(priority)
    return proxies, report, priority


# ──────────────────────────────────────────────────────────────
#  RESOLUCIÓN DE PAÍS EN LOTE (revela LATAM/PE ocultas en "??")
# ──────────────────────────────────────────────────────────────
async def geo_resolve(addresses):
    """
    Resuelve el país de una lista de 'ip:port' usando ip-api batch
    (100 IPs/request, ~15 req/min). Devuelve {ip: 'CC'}.

    El check de vida se satura con el lookup geo (ip-api 40/min unkeyed),
    dejando muchas proxies como '??'. Este batch las recupera: 100 IPs por
    request en vez de 1, así afloran las peruanas/LATAM que sí teníamos vivas.
    """
    ips = []
    seen = set()
    for a in addresses:
        ip = a.split(":")[0]
        if ip not in seen and engine._valid_ip(ip):
            seen.add(ip)
            ips.append(ip)

    out = {}
    if not ips:
        return out
    fields = "status,countryCode,query"
    # Presupuesto de espera total (s) para aguantar rate-limits de ip-api.
    # Tras una cosecha/verify, ip-api suele estar saturado; respetamos X-Ttl.
    wait_budget = 240.0

    async with aiohttp.ClientSession() as session:
        i = 0
        while i < len(ips):
            batch = ips[i:i + 100]
            payload = [{"query": ip, "fields": fields} for ip in batch]
            try:
                async with session.post(
                    "http://ip-api.com/batch",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 429:
                        # Rate limit: ip-api dice en X-Ttl los segundos hasta el reset.
                        ttl = 0
                        try:
                            ttl = int(resp.headers.get("X-Ttl", "0") or 0)
                        except ValueError:
                            ttl = 0
                        wait = min(max(ttl + 1, 2), 65)
                        if wait_budget - wait < 0:
                            break  # sin presupuesto: salir con lo que haya
                        wait_budget -= wait
                        await asyncio.sleep(wait)
                        continue  # reintentar EL MISMO lote (no avanzar i)
                    if resp.status != 200:
                        i += 100
                        continue
                    rl_remaining = resp.headers.get("X-Rl")
                    data = await resp.json()
                for item in data:
                    cc = item.get("countryCode")
                    q = item.get("query")
                    if q and cc:
                        out[q] = cc.upper()
            except Exception:
                i += 100
                continue
            i += 100
            # Si quedan pocas requests en la ventana, espera al reset.
            try:
                if rl_remaining is not None and int(rl_remaining) <= 1 and i < len(ips):
                    await asyncio.sleep(4.2)
                elif i < len(ips):
                    await asyncio.sleep(1.0)
            except (ValueError, TypeError):
                if i < len(ips):
                    await asyncio.sleep(4.2)
    return out
