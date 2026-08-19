"""
Proxy Checker Pro - Web Backend (FastAPI + WebSocket)
=====================================================
Envuelve el motor async `proxy_checker_v2` y transmite el progreso
de verificación en vivo por WebSocket.
"""

import os
import re
import sys
import json
import uuid
import secrets
import asyncio
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, Query, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse

# ── Importar el motor (raíz del repo) ──
ENGINE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ENGINE_DIR))
import proxy_checker_v2 as engine  # noqa: E402

# ── Lógica anti-ban (selección geo-cercana, módulo local) ──
import antiban  # noqa: E402

# ── Cosechador geo-dirigido (LATAM-first, opcional vía nuestras proxies) ──
try:
    import harvester  # noqa: E402
except Exception as _e:  # no romper el arranque si falta aiohttp/módulo
    harvester = None
    print(f"[harvester] no disponible: {_e}")

app = FastAPI(title="Proxy Checker Pro - Web", version="1.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Token de admin (si está vacío, el panel admin queda abierto = solo uso local)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


async def require_admin(x_admin_token: str = Header(None)):
    if ADMIN_TOKEN and x_admin_token != ADMIN_TOKEN:
        raise HTTPException(403, "Token de admin inválido")
    return True

# ══════════════════════════════════════════════════════════════
#   BAÚL DE PROXIES (persistencia SQLite)
# ══════════════════════════════════════════════════════════════
VAULT_DB = str(Path(__file__).resolve().parent / "vault.db")


def _db():
    conn = sqlite3.connect(VAULT_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_vault():
    with _db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS vault (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                protocol TEXT, score INTEGER, quality TEXT,
                anon_level TEXT, country TEXT, latency_ms REAL,
                note TEXT DEFAULT '', saved_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                label TEXT DEFAULT '',
                active INTEGER DEFAULT 1,
                requests INTEGER DEFAULT 0,
                created_at TEXT,
                last_used TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                k TEXT PRIMARY KEY,
                v TEXT
            )
        """)
        # ── Migraciones (columnas nuevas) ──
        def addcol(table, col, ddl):
            cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        addcol("api_keys", "rate_limit", "rate_limit INTEGER DEFAULT 0")       # req/día (0 = ilimitado)
        addcol("api_keys", "requests_today", "requests_today INTEGER DEFAULT 0")
        addcol("api_keys", "day", "day TEXT DEFAULT ''")
        addcol("vault", "checks", "checks INTEGER DEFAULT 0")
        addcol("vault", "fails", "fails INTEGER DEFAULT 0")
        addcol("vault", "last_check", "last_check TEXT DEFAULT ''")


init_vault()


def _get_setting(k, default=None):
    with _db() as c:
        row = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    return row["v"] if row else default


def _set_setting(k, v):
    with _db() as c:
        c.execute("INSERT INTO settings (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=?", (k, str(v), str(v)))


def _fresh_window_min() -> int:
    """Ventana de frescura (min). Solo se entregan proxies verificadas dentro de ella."""
    try:
        return max(1, int(_get_setting("fresh_window_min", "30") or 30))
    except (TypeError, ValueError):
        return 30


def _bump_checked(n: int):
    """Acumula cuántas proxies se han verificado HOY (para /api/pool/stats)."""
    if n <= 0:
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _get_setting("checked_day", "") != today:
        _set_setting("checked_day", today)
        _set_setting("checked_today", 0)
    cur = int(_get_setting("checked_today", "0") or 0)
    _set_setting("checked_today", cur + n)


def _checked_today() -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _get_setting("checked_day", "") != today:
        return 0
    return int(_get_setting("checked_today", "0") or 0)


def _key_to_dict(row, mask=False):
    d = dict(row)
    if mask and d.get("key"):
        k = d["key"]
        d["key"] = k[:10] + "…" + k[-4:]
    return d


class RateLimited(Exception):
    pass


def validate_key(k: str):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    with _db() as c:
        row = c.execute("SELECT * FROM api_keys WHERE key=? AND active=1", (k,)).fetchone()
        if not row:
            return None
        d = dict(row)
        # Reset diario del contador
        used_today = d.get("requests_today", 0) if d.get("day") == today else 0
        limit = d.get("rate_limit", 0) or 0
        if limit and used_today >= limit:
            raise RateLimited()
        c.execute(
            "UPDATE api_keys SET requests=requests+1, requests_today=?, day=?, last_used=? WHERE id=?",
            (used_today + 1, today, now, d["id"]),
        )
        d["requests_today"] = used_today + 1
        return d


async def require_key(x_api_key: str = Header(None), key: str = Query(None)):
    k = x_api_key or key
    if not k:
        raise HTTPException(401, "API key requerida (header 'X-API-Key' o ?key=...)")
    try:
        row = validate_key(k)
    except RateLimited:
        raise HTTPException(429, "Límite diario de la API key alcanzado")
    if not row:
        raise HTTPException(403, "API key inválida o revocada")
    return row


async def require_key_antiban(x_api_key: str = Header(None), key: str = Query(None)):
    """Auth para /api/antiban/proxy. Igual que require_key (API key + rate limit)
    PERO permite acceso libre si ANTIBAN_PUBLIC=1, para no romper el uso interno
    del Marketplace (que consume este pool anti-ban sin credencial)."""
    if os.getenv("ANTIBAN_PUBLIC", "0") == "1":
        return {"public": True}
    return await require_key(x_api_key, key)


# Estado de rotación en memoria (round-robin por filtro)
_rot_idx = {}


def _vault_rows():
    with _db() as c:
        rows = c.execute("SELECT * FROM vault ORDER BY score DESC, saved_at DESC").fetchall()
    return [dict(r) for r in rows]

# ── Mapeo de targets (igual que el CLI) ──
def resolve_targets(tests: str, custom_url: str = "") -> list:
    if tests == "alive":
        return []
    if tests == "google":
        return ["google.com", "cloudflare"]
    if tests == "hq":
        return list(engine.Config.HQ_TEST_URLS.keys())
    if tests == "custom":
        url = custom_url or "https://www.google.com/"
        if not url.startswith("http"):
            url = "https://" + url
        return [f"custom:{url}"]
    return []


def parse_pasted(text: str) -> dict:
    """Parsea proxies pegadas (una por línea, detecta protocolo por prefijo)."""
    proxies = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)', line)
        if not m:
            continue
        ip, port = m.group(1), m.group(2)
        if not engine._valid_ip(ip) or not (1 <= int(port) <= 65535):
            continue
        addr = f"{ip}:{port}"
        low = line.lower()
        if "socks5" in low:
            proto = engine.ProxyProtocol.SOCKS5
        elif "socks4" in low:
            proto = engine.ProxyProtocol.SOCKS4
        elif "https" in low:
            proto = engine.ProxyProtocol.HTTPS
        else:
            proto = engine.ProxyProtocol.HTTP
        proxies[addr] = proto
    return proxies


async def fetch_proxies(source: str, pasted: str = "") -> dict:
    P = engine.ProxyProtocol
    if source == "paste":
        return parse_pasted(pasted)
    if source == "http":
        return await engine.ProxyFetcher.fetch_all(protocols_filter={P.HTTP, P.HTTPS})
    if source == "socks":
        return await engine.ProxyFetcher.fetch_all(protocols_filter={P.SOCKS4, P.SOCKS5})
    if source == "api":
        return await engine.ProxyFetcher.fetch_all(source_type_filter="api")
    if source == "github":
        return await engine.ProxyFetcher.fetch_all(source_type_filter="github")
    return await engine.ProxyFetcher.fetch_all()


@app.get("/api/health")
async def health():
    return {"status": "ok", "engine": "proxy_checker_v2", "version": "1.0.0"}


@app.post("/api/test-one")
async def test_one(payload: dict):
    """Prueba rápida de UN solo proxy (vida + anonimato + país + score)."""
    proxy_str = (payload or {}).get("proxy", "").strip()
    deep = bool((payload or {}).get("deep", False))
    proxies = parse_pasted(proxy_str)
    if not proxies:
        return {"ok": False, "error": "Formato inválido. Usa ip:puerto (opcional socks5://)"}

    # Tomar solo el primero
    addr = next(iter(proxies))
    one = {addr: proxies[addr]}
    targets = ["google.com", "cloudflare"] if deep else []
    engine.Config.MAX_CONCURRENT = 5
    stats = engine.Stats()
    checker = engine.ProxyChecker(stats, test_targets=targets)
    await checker.check_all(one)

    if checker.results:
        r = checker.results[0]
        return {"ok": True, "alive": True, "result": r.to_dict()}
    return {"ok": True, "alive": False, "address": addr}


@app.post("/api/clean")
async def clean_list(payload: dict):
    """Limpia, normaliza y deduplica una lista de proxies pegada."""
    text = (payload or {}).get("text", "")
    raw_lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    proxies = parse_pasted(text)  # dedupe vía dict + validación de IP/puerto

    by_protocol = {}
    plain = []
    prefixed = []
    for addr, proto in proxies.items():
        by_protocol[proto.value] = by_protocol.get(proto.value, 0) + 1
        plain.append(addr)
        prefixed.append(f"{proto.value}://{addr}")

    return {
        "ok": True,
        "input_lines": len(raw_lines),
        "valid": len(proxies),
        "removed": max(0, len(raw_lines) - len(proxies)),
        "by_protocol": by_protocol,
        "plain": plain,
        "prefixed": prefixed,
    }


# ── BAÚL: endpoints ──
@app.get("/api/vault")
async def vault_list():
    rows = _vault_rows()
    return {"total": len(rows), "proxies": rows}


@app.post("/api/vault")
async def vault_add(payload: dict):
    """Guarda uno o varios proxies en el baúl (dedup por address)."""
    items = (payload or {}).get("proxies", [])
    if isinstance(items, dict):
        items = [items]
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    with _db() as c:
        for p in items:
            addr = p.get("address") or f"{p.get('ip','')}:{p.get('port','')}"
            if not addr or ":" not in addr:
                continue
            try:
                # last_check=now: proxy recién testeada por el cliente => fresca.
                c.execute(
                    "INSERT OR IGNORE INTO vault (address, protocol, score, quality, anon_level, country, latency_ms, note, saved_at, last_check)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (addr, p.get("protocol", ""), int(p.get("score", 0) or 0), p.get("quality", ""),
                     p.get("anon_level", ""), p.get("country", ""), float(p.get("latency_ms", 0) or 0),
                     p.get("note", ""), now, now),
                )
                if c.total_changes:
                    added += 1
            except Exception:
                continue
    rows = _vault_rows()
    return {"ok": True, "added": added, "total": len(rows), "proxies": rows}


@app.delete("/api/vault/{pid}")
async def vault_delete(pid: int):
    with _db() as c:
        c.execute("DELETE FROM vault WHERE id=?", (pid,))
    return {"ok": True, "total": len(_vault_rows())}


@app.delete("/api/vault")
async def vault_clear(_: bool = Depends(require_admin)):
    with _db() as c:
        c.execute("DELETE FROM vault")
    return {"ok": True, "total": 0}


async def _do_refresh(limit: int = 600) -> dict:
    """Escaneo rápido (APIs, solo vida) y agrega las vivas al baúl."""
    engine.Config.MAX_CONCURRENT = 500
    proxies = await fetch_proxies("api")
    if limit and limit < len(proxies):
        import random
        items = list(proxies.items()); random.shuffle(items)
        proxies = dict(items[:limit])
    stats = engine.Stats()
    checker = engine.ProxyChecker(stats, test_targets=[])
    await checker.check_all(proxies)
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    with _db() as c:
        for r in checker.results:
            d = r.to_dict()
            try:
                # last_check=now: la proxy acaba de pasar el chequeo de vida.
                c.execute(
                    "INSERT OR IGNORE INTO vault (address, protocol, score, quality, anon_level, country, latency_ms, note, saved_at, last_check)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (d["address"], d["protocol"], d["score"], d["quality"], d["anon_level"],
                     d["country"], d["latency_ms"], "auto", now, now),
                )
                if c.total_changes:
                    added += 1
            except Exception:
                continue
    _bump_checked(stats.checked)
    _set_setting("last_refresh", now)
    return {"ok": True, "checked": stats.checked, "alive": stats.alive, "added": added, "total": len(_vault_rows())}


@app.post("/api/vault/refresh")
async def vault_refresh(payload: dict = None, _: bool = Depends(require_admin)):
    payload = payload or {}
    return await _do_refresh(int(payload.get("limit", 600)))


def _store_alive(results, note="harvest") -> int:
    """Inserta los resultados VIVOS de un checker en el baúl (dedup por address)."""
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    with _db() as c:
        for r in results:
            d = r.to_dict()
            try:
                c.execute(
                    "INSERT OR IGNORE INTO vault (address, protocol, score, quality, anon_level, country, latency_ms, note, saved_at, last_check)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (d["address"], d["protocol"], d["score"], d["quality"], d["anon_level"],
                     d["country"], d["latency_ms"], note, now, now),
                )
                if c.total_changes:
                    added += 1
            except Exception:
                continue
    return added


async def _do_harvest(countries=None, via_pool=True, limit=4000) -> dict:
    """
    Cosecha geo-dirigida (LATAM-first): baja fuentes por país (opcional vía
    nuestras propias proxies vivas para esquivar rate-limits), verifica vida
    con el motor y agrega las vivas al baúl. Devuelve un reporte con conteo
    por país de las NUEVAS proxies vivas.
    """
    if harvester is None:
        return {"ok": False, "error": "harvester no disponible (falta aiohttp?)"}

    via_rows = _vault_rows() if via_pool else None
    raw, hreport, priority = await harvester.harvest(via_proxies=via_rows, countries=countries)
    if not raw:
        return {"ok": True, "harvested_raw": 0, "checked": 0, "alive": 0,
                "added": 0, "report": hreport, "total": len(_vault_rows())}

    # No re-verificar las que ya tenemos en el baúl (ahorra presupuesto de check).
    known = {r["address"] for r in _vault_rows()}

    # Presupuesto de verificación: PRIORITARIAS primero (fuentes pre-validadas /
    # geo-dirigidas = alta tasa de vivas), luego rellenar con bulk aleatorio.
    import random
    prio_items = [(a, p) for a, p in raw.items() if a in priority and a not in known]
    bulk_items = [(a, p) for a, p in raw.items() if a not in priority and a not in known]
    random.shuffle(prio_items)
    random.shuffle(bulk_items)
    selected = prio_items[:limit] if limit else prio_items
    n_prio_checked = len(selected)
    if limit and len(selected) < limit:
        selected += bulk_items[:limit - len(selected)]
    elif not limit:
        selected += bulk_items
    raw = dict(selected)

    engine.Config.MAX_CONCURRENT = 500
    stats = engine.Stats()
    checker = engine.ProxyChecker(stats, test_targets=[])
    await checker.check_all(raw)
    added = _store_alive(checker.results, note="harvest")
    _bump_checked(stats.checked)
    _set_setting("last_refresh", datetime.now(timezone.utc).isoformat())
    _set_setting("last_harvest", datetime.now(timezone.utc).isoformat())

    # Conteo por país de las proxies vivas cosechadas (lo valioso: LATAM).
    by_country = {}
    for r in checker.results:
        cc = (r.to_dict().get("country") or "??").upper()
        by_country[cc] = by_country.get(cc, 0) + 1

    return {
        "ok": True,
        "harvested_raw": hreport["unique"],
        "via_proxy": hreport["via_proxy"],
        "checked": stats.checked,
        "alive": stats.alive,
        "added": added,
        "alive_by_country": dict(sorted(by_country.items(), key=lambda x: -x[1])),
        "priority_pool": hreport.get("priority"),
        "priority_checked": n_prio_checked,
        "sources_ok": hreport["ok"],
        "sources_total": hreport["sources"],
        "total": len(_vault_rows()),
    }


async def _do_geo_resolve(only_unknown=True) -> dict:
    """Resuelve país de las proxies del baúl con país '??' (o todas) en lote."""
    if harvester is None:
        return {"ok": False, "error": "harvester no disponible"}
    rows = _vault_rows()
    targets = [r["address"] for r in rows
               if (not only_unknown) or (r.get("country") or "??") in ("", "??", "Unknown")]
    if not targets:
        return {"ok": True, "resolved": 0, "updated": 0, "by_country": {}}
    ip_cc = await harvester.geo_resolve(targets)
    updated = 0
    by_country = {}
    with _db() as c:
        for r in rows:
            ip = r["address"].split(":")[0]
            cc = ip_cc.get(ip)
            if not cc:
                continue
            if (r.get("country") or "??") != cc:
                c.execute("UPDATE vault SET country=? WHERE id=?", (cc, r["id"]))
                updated += 1
            by_country[cc] = by_country.get(cc, 0) + 1
    return {"ok": True, "resolved": len(ip_cc), "updated": updated,
            "by_country": dict(sorted(by_country.items(), key=lambda x: -x[1]))}


@app.post("/api/vault/geo-resolve")
async def geo_resolve_endpoint(payload: dict = None, _: bool = Depends(require_admin)):
    """Resuelve el país de las proxies '??' del baúl (ip-api batch)."""
    payload = payload or {}
    only_unknown = bool(payload.get("only_unknown", True))
    return await _do_geo_resolve(only_unknown=only_unknown)


@app.post("/api/harvest")
async def harvest_endpoint(payload: dict = None, _: bool = Depends(require_admin)):
    """
    Cosecha proxies geo-dirigidas (LATAM-first). Body opcional:
      countries: ["PE","EC",...]  (default: LATAM)
      via_pool:  true|false       (rutea descarga por nuestras proxies vivas)
      limit:     máx a verificar  (default 4000)
    """
    payload = payload or {}
    countries = payload.get("countries") or None
    via_pool = bool(payload.get("via_pool", True))
    limit = int(payload.get("limit", 4000))
    return await _do_harvest(countries=countries, via_pool=via_pool, limit=limit)


async def _do_verify(prune: bool = True) -> dict:
    """Re-verifica los proxies del baúl: actualiza uptime/score y elimina los muertos."""
    rows = _vault_rows()
    if not rows:
        return {"ok": True, "checked": 0, "alive": 0, "removed": 0, "total": 0}
    proxies = {}
    for r in rows:
        proto = r["protocol"]
        try:
            proxies[r["address"]] = engine.ProxyProtocol(proto)
        except Exception:
            proxies[r["address"]] = engine.ProxyProtocol.HTTP
    engine.Config.MAX_CONCURRENT = 300
    stats = engine.Stats()
    checker = engine.ProxyChecker(stats, test_targets=[])
    await checker.check_all(proxies)
    alive_map = {res.address: res.to_dict() for res in checker.results}
    now = datetime.now(timezone.utc).isoformat()
    removed = 0
    with _db() as c:
        for r in rows:
            addr = r["address"]
            checks = (r.get("checks") or 0) + 1
            if addr in alive_map:
                d = alive_map[addr]
                c.execute(
                    "UPDATE vault SET score=?, latency_ms=?, anon_level=?, quality=?, checks=?, last_check=? WHERE id=?",
                    (d["score"], d["latency_ms"], d["anon_level"], d["quality"], checks, now, r["id"]),
                )
            else:
                fails = (r.get("fails") or 0) + 1
                if prune:
                    c.execute("DELETE FROM vault WHERE id=?", (r["id"],))
                    removed += 1
                else:
                    c.execute("UPDATE vault SET fails=?, checks=?, last_check=? WHERE id=?",
                              (fails, checks, now, r["id"]))
    _bump_checked(len(rows))
    _set_setting("last_refresh", now)
    return {"ok": True, "checked": len(rows), "alive": len(alive_map), "removed": removed, "total": len(_vault_rows())}


@app.post("/api/vault/verify")
async def vault_verify(payload: dict = None, _: bool = Depends(require_admin)):
    payload = payload or {}
    return await _do_verify(prune=bool(payload.get("prune", True)))


# ══════════════════════════════════════════════════════════════
#   SCHEDULER — auto-refresh del baúl en segundo plano
# ══════════════════════════════════════════════════════════════
_scheduler_task = None
_scheduler_state = {"running": False, "last_run": None, "last_result": None}


async def _scheduler_loop():
    _scheduler_state["running"] = True
    try:
        while _get_setting("sched_enabled", "0") == "1":
            interval = int(_get_setting("sched_interval", "30"))
            try:
                res = await _do_refresh(int(_get_setting("sched_limit", "600")))
                # Cosecha geo-dirigida LATAM (opcional): trae más proxies por país.
                if _get_setting("sched_harvest", "0") == "1":
                    try:
                        hres = await _do_harvest(via_pool=True,
                                                 limit=int(_get_setting("sched_harvest_limit", "3000")))
                        res["harvest"] = {"added": hres.get("added"),
                                          "alive_by_country": hres.get("alive_by_country")}
                    except Exception as he:
                        res["harvest"] = {"error": str(he)}
                if _get_setting("sched_verify", "1") == "1":
                    await _do_verify(prune=True)
                # Resolver país de las '??' (revela LATAM/PE ocultas).
                if _get_setting("sched_geo", "1") == "1":
                    try:
                        await _do_geo_resolve(only_unknown=True)
                    except Exception:
                        pass
                _scheduler_state["last_run"] = datetime.now(timezone.utc).isoformat()
                _scheduler_state["last_result"] = res
            except Exception as e:
                _scheduler_state["last_result"] = {"error": str(e)}
            for _ in range(max(1, interval) * 60):
                if _get_setting("sched_enabled", "0") != "1":
                    break
                await asyncio.sleep(1)
    finally:
        _scheduler_state["running"] = False


def _ensure_scheduler():
    global _scheduler_task
    if _get_setting("sched_enabled", "0") == "1" and (_scheduler_task is None or _scheduler_task.done()):
        _scheduler_task = asyncio.create_task(_scheduler_loop())


@app.on_event("startup")
async def _on_startup():
    # Validación continua 24/7: si ALWAYS_FRESH=1, activa el loop de revalidación
    # del baúl al arrancar para que SIEMPRE haya pool vivo (poda muertas cada N min).
    if os.getenv("ALWAYS_FRESH", "0") == "1":
        _set_setting("antiban_enabled", "1")
    _ensure_scheduler()
    _ensure_antiban_scheduler()


@app.get("/api/scheduler")
async def scheduler_status():
    return {
        "enabled": _get_setting("sched_enabled", "0") == "1",
        "interval": int(_get_setting("sched_interval", "30")),
        "limit": int(_get_setting("sched_limit", "600")),
        "verify": _get_setting("sched_verify", "1") == "1",
        "harvest": _get_setting("sched_harvest", "0") == "1",
        "harvest_limit": int(_get_setting("sched_harvest_limit", "3000")),
        "geo": _get_setting("sched_geo", "1") == "1",
        "running": _scheduler_state["running"],
        "last_run": _scheduler_state["last_run"],
        "last_result": _scheduler_state["last_result"],
        "last_harvest": _get_setting("last_harvest", None),
    }


@app.post("/api/scheduler")
async def scheduler_set(payload: dict, _: bool = Depends(require_admin)):
    if "enabled" in payload:
        _set_setting("sched_enabled", "1" if payload["enabled"] else "0")
    if "interval" in payload:
        _set_setting("sched_interval", max(1, int(payload["interval"])))
    if "limit" in payload:
        _set_setting("sched_limit", max(100, int(payload["limit"])))
    if "verify" in payload:
        _set_setting("sched_verify", "1" if payload["verify"] else "0")
    if "harvest" in payload:
        _set_setting("sched_harvest", "1" if payload["harvest"] else "0")
    if "harvest_limit" in payload:
        _set_setting("sched_harvest_limit", max(500, int(payload["harvest_limit"])))
    if "geo" in payload:
        _set_setting("sched_geo", "1" if payload["geo"] else "0")
    _ensure_scheduler()
    return await scheduler_status()


# ══════════════════════════════════════════════════════════════
#   ROTADOR EN VIVO (gated por API key) — para vender acceso
# ══════════════════════════════════════════════════════════════
def _proxy_payload(p: dict) -> dict:
    """Normaliza una fila del baúl al JSON de entrega de /api/proxy."""
    return {
        "proxy": f"{p.get('protocol','http')}://{p['address']}",
        "address": p["address"], "protocol": p.get("protocol"),
        "score": p.get("score"), "quality": p.get("quality"),
        "anon_level": p.get("anon_level"), "country": p.get("country"),
        "latency_ms": p.get("latency_ms"), "last_checked": p.get("last_check"),
    }


def _delivery_candidates(country, min_score, protocol, window):
    """
    Candidatos de ENTREGA: solo proxies FRESCAS (verificadas dentro de la
    ventana) ordenadas geo-cercanas (lógica antiban) cuando se pide un país,
    o por score descendente cuando no.
    """
    fresh = antiban.filter_fresh(_vault_rows(), window)
    if country:
        # Geo-prioriza con la misma lógica del anti-ban (sin tope de latencia).
        return antiban.select_antiban(
            fresh, country=country, min_score=min_score,
            max_latency=float("inf"), protocol=protocol,
        )
    out = []
    proto = (protocol or "").lower().strip() or None
    for r in fresh:
        if int(r.get("score") or 0) < min_score:
            continue
        if proto and (r.get("protocol") or "").lower() != proto:
            continue
        out.append(r)
    out.sort(key=lambda r: -(int(r.get("score") or 0)))
    return out


@app.get("/api/proxy")
async def rotate_proxy(
    protocol: str = Query(None),
    min_score: int = Query(0),
    country: str = Query(None),
    count: int = Query(1),
    format: str = Query("json"),
    keyrow: dict = Depends(require_key),
):
    """
    API DE ENTREGA (producto central). Devuelve proxies VIVAS verificadas
    recientemente (geo-priorizadas con la lógica anti-ban). Requiere API key
    + rate limit (ver require_key). El cliente NO testea: consume.

    Query:
      key / X-API-Key  -> credencial (obligatoria)
      country=PE       -> país objetivo (geo-prioriza vecinos cercanos)
      protocol=http    -> filtra protocolo (http/https/socks4/socks5)
      count=10         -> cuántas proxies devolver (1..100, round-robin)
      min_score=50     -> score mínimo
      format=json|text -> text = una por línea `proto://ip:port`

    Garantía de frescura: solo entrega proxies con last_check dentro de
    `fresh_window_min` (default 30). Si no hay suficientes frescas, dispara
    una verificación bajo demanda y reintenta.
    """
    count = max(1, min(int(count), 100))
    window = _fresh_window_min()

    rows = _delivery_candidates(country, min_score, protocol, window)
    if len(rows) < count:
        # No hay suficientes frescas: re-verificar el baúl y reintentar.
        await _ensure_fresh_pool(country)
        rows = _delivery_candidates(country, min_score, protocol, window)

    if not rows:
        raise HTTPException(404, "No hay proxies frescas que cumplan el filtro")

    sig = f"{protocol}|{min_score}|{country}"
    i = _rot_idx.get(sig, 0)
    n = len(rows)
    picked = [rows[(i + j) % n] for j in range(min(count, n))]
    _rot_idx[sig] = (i + len(picked)) % n

    if format == "text":
        body = "\n".join(f"{p.get('protocol','http')}://{p['address']}" for p in picked)
        return PlainTextResponse(body)

    if count == 1:
        # Compat: respuesta de objeto único (contrato histórico).
        out = _proxy_payload(picked[0])
        out["pool_size"] = n
        return out
    return {
        "count": len(picked), "pool_size": n,
        "fresh_window_min": window,
        "proxies": [_proxy_payload(p) for p in picked],
    }


# ══════════════════════════════════════════════════════════════
#   MÉTRICAS DE CONFIANZA DEL POOL (público)
# ══════════════════════════════════════════════════════════════
@app.get("/api/pool/stats")
async def pool_stats():
    """
    Métricas de confianza del pool premium (público, sin API key).
    Solo cuenta proxies FRESCAS (verificadas dentro de fresh_window_min).
    """
    window = _fresh_window_min()
    stats = antiban.compute_pool_stats(_vault_rows(), fresh_window_min=window)
    stats["last_refresh"] = _get_setting("last_refresh", None)
    stats["total_checked_today"] = _checked_today()
    return stats


# ══════════════════════════════════════════════════════════════
#   CONSUMO POR API KEY (planes por consumo)
# ══════════════════════════════════════════════════════════════
@app.get("/api/usage")
async def usage(key: str = Query(None), x_api_key: str = Header(None)):
    """
    Consumo del día de una API key vs su límite (plan por consumo).
    NO incrementa el contador (solo lectura). rate_limit=0 => ilimitado.
    """
    k = x_api_key or key
    if not k:
        raise HTTPException(401, "API key requerida (header 'X-API-Key' o ?key=...)")
    with _db() as c:
        row = c.execute("SELECT * FROM api_keys WHERE key=?", (k,)).fetchone()
    if not row:
        raise HTTPException(403, "API key inválida")
    d = dict(row)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    used = d.get("requests_today", 0) if d.get("day") == today else 0
    limit = d.get("rate_limit", 0) or 0
    return {
        "label": d.get("label", ""),
        "active": bool(d.get("active", 1)),
        "day": today,
        "used_today": used,
        "limit": limit,
        "unlimited": limit == 0,
        "remaining": (max(0, limit - used) if limit else None),
        "total_requests": d.get("requests", 0),
        "last_used": d.get("last_used"),
    }


# ══════════════════════════════════════════════════════════════
#   ANTI-BAN POOL — proxies geo-cercanos y estables para FB
# ══════════════════════════════════════════════════════════════
# UN SOLO MOTOR, DOS PRODUCTOS: este pool (baúl + scheduler + verify) es la
# ÚNICA fuente. Producto 1 = venta de proxies vivas vía /api/proxy (con key).
# Producto 2 = Marketplace anti-ban, que consume ESTE MISMO pool vía
# /api/antiban/proxy (geo-cercano sticky). No se duplica el motor.
# Objetivo: dar a cada cuenta un proxy del mismo país (o vecino cercano),
# rápido y elite, para evitar baneos al automatizar. Reusa el baúl como
# fuente; si está vacío, dispara un fetch+check acotado (~800) y cachea.

# Tamaño de la muestra a escanear cuando el baúl está vacío.
ANTIBAN_BOOTSTRAP_SAMPLE = 800

# Candado para evitar varios bootstraps simultáneos.
_antiban_bootstrap_lock = asyncio.Lock()

# Estado del refresco anti-ban en segundo plano.
_antiban_task = None
_antiban_state = {"running": False, "last_run": None, "last_result": None}


async def _ensure_antiban_pool() -> list:
    """
    Devuelve las filas del baúl; si está vacío, dispara un escaneo acotado
    (fetch APIs + check de vida) y las cachea en el baúl antes de devolver.
    """
    rows = _vault_rows()
    if rows:
        return rows
    # El baúl está vacío: bootstrap acotado (protegido por candado).
    async with _antiban_bootstrap_lock:
        rows = _vault_rows()  # re-chequear: otra request pudo llenarlo
        if rows:
            return rows
        try:
            await _do_refresh(ANTIBAN_BOOTSTRAP_SAMPLE)
        except Exception as e:
            # No reventar el endpoint si el fetch falla; devolver lo que haya.
            print(f"[antiban] bootstrap falló: {e}")
        rows = _vault_rows()
    return rows


async def _ensure_fresh_pool(country: str = None) -> list:
    """
    Garantiza que haya proxies FRESCAS para entregar. Re-verifica el baúl
    (actualiza last_check y poda muertas); si tras eso no queda ninguna
    fresca, dispara un fetch acotado y vuelve a verificar. Protegido por
    candado para no lanzar varios escaneos simultáneos.
    """
    window = _fresh_window_min()
    async with _antiban_bootstrap_lock:
        if antiban.filter_fresh(_vault_rows(), window):
            return _vault_rows()  # otra request ya lo refrescó
        if _vault_rows():
            await _do_verify(prune=True)
        if not antiban.filter_fresh(_vault_rows(), window):
            try:
                await _do_refresh(ANTIBAN_BOOTSTRAP_SAMPLE)
                await _do_verify(prune=True)
            except Exception as e:
                print(f"[fresh] refresco bajo demanda falló: {e}")
    return _vault_rows()


def _antiban_payload(p: dict) -> dict:
    """Normaliza una fila del baúl al JSON anti-ban (campos esenciales)."""
    return {
        "address": p.get("address"),
        "proxy": f"{p.get('protocol','http')}://{p.get('address')}",
        "country": p.get("country"),
        "protocol": p.get("protocol"),
        "score": p.get("score"),
        "latency_ms": p.get("latency_ms"),
        "anon": p.get("anon_level"),
        "last_checked": p.get("last_check"),
    }


@app.get("/api/antiban/proxy")
async def antiban_proxy(
    country: str = Query("PE"),
    max_latency: float = Query(3000.0),
    min_score: int = Query(50),
    protocol: str = Query(None),
    format: str = Query("json"),
    keyrow: dict = Depends(require_key_antiban),
):
    """
    Devuelve el MEJOR proxy anti-ban para un país (sticky por cuenta).

    Pensado para que el consumidor lo FIJE por cuenta: siempre devuelve el
    mejor disponible (mismo país > vecino cercano), por lo que llamar de nuevo
    suele dar el mismo proxy mientras siga vivo en el baúl.

    AUTH (cambio de endurecimiento): este endpoint ahora requiere API key
    (header 'X-API-Key' o ?key=...) igual que /api/proxy. Excepcion: si la
    variable de entorno ANTIBAN_PUBLIC=1, el acceso es libre, para no romper el
    uso interno del Marketplace (que lo consume sin credencial). En produccion,
    deja ANTIBAN_PUBLIC sin definir (o =0) para exigir API key a terceros.
    """
    rows = await _ensure_antiban_pool()
    window = _fresh_window_min()
    # Garantía de frescura: solo proxies verificadas dentro de la ventana.
    fresh = antiban.filter_fresh(rows, window)
    if not fresh:
        fresh = antiban.filter_fresh(await _ensure_fresh_pool(country), window)
    best = antiban.best_antiban(
        fresh, country=country, min_score=min_score,
        max_latency=max_latency, protocol=protocol,
    )
    if not best:
        raise HTTPException(404, "No hay proxies anti-ban frescas que cumplan el filtro")
    if format == "text":
        return PlainTextResponse(f"{best.get('protocol','http')}://{best.get('address')}")
    return _antiban_payload(best)


@app.get("/api/antiban/pool")
async def antiban_pool(
    country: str = Query("PE"),
    max_latency: float = Query(3000.0),
    min_score: int = Query(50),
    protocol: str = Query(None),
    limit: int = Query(50),
):
    """Lista de candidatos anti-ban (ordenados de mejor a peor)."""
    rows = await _ensure_antiban_pool()
    window = _fresh_window_min()
    fresh = antiban.filter_fresh(rows, window)
    if not fresh:
        fresh = antiban.filter_fresh(await _ensure_fresh_pool(country), window)
    sel = antiban.select_antiban(
        fresh, country=country, min_score=min_score,
        max_latency=max_latency, protocol=protocol, limit=limit,
    )
    return {
        "country": (country or "PE").upper(),
        "total": len(sel),
        "filters": {"min_score": min_score, "max_latency": max_latency,
                    "protocol": protocol},
        "proxies": [_antiban_payload(p) for p in sel],
    }


# ── Refresco anti-ban en segundo plano (revalida cada N min, default 30) ──
async def _antiban_loop():
    """
    Mantiene fresco el pool geo-cercano: cada N minutos re-verifica el baúl
    (descarta muertos y actualiza score/latencia) y, si quedó por debajo del
    mínimo de candidatos para el país objetivo, dispara un fetch acotado.
    """
    _antiban_state["running"] = True
    try:
        while _get_setting("antiban_enabled", "0") == "1":
            interval = int(_get_setting("antiban_interval", "30"))
            country = _get_setting("antiban_country", antiban.DEFAULT_COUNTRY)
            min_pool = int(_get_setting("antiban_min_pool", "20"))
            try:
                # 1) Re-verificar el baúl (poda muertos, actualiza métricas).
                await _do_verify(prune=True)
                # 2) Si el pool geo-cercano quedó corto, traer más proxies.
                rows = _vault_rows()
                sel = antiban.select_antiban(rows, country=country)
                if len(sel) < min_pool:
                    await _do_refresh(ANTIBAN_BOOTSTRAP_SAMPLE)
                    rows = _vault_rows()
                    sel = antiban.select_antiban(rows, country=country)
                _antiban_state["last_run"] = datetime.now(timezone.utc).isoformat()
                _antiban_state["last_result"] = {
                    "country": (country or "PE").upper(),
                    "pool_size": len(sel),
                    "vault_total": len(rows),
                }
            except Exception as e:
                _antiban_state["last_result"] = {"error": str(e)}
            # Espera troceada para poder apagar el loop rápido.
            for _ in range(max(1, interval) * 60):
                if _get_setting("antiban_enabled", "0") != "1":
                    break
                await asyncio.sleep(1)
    finally:
        _antiban_state["running"] = False


def _ensure_antiban_scheduler():
    global _antiban_task
    if _get_setting("antiban_enabled", "0") == "1" and (_antiban_task is None or _antiban_task.done()):
        _antiban_task = asyncio.create_task(_antiban_loop())


@app.get("/api/antiban/scheduler")
async def antiban_scheduler_status():
    return {
        "enabled": _get_setting("antiban_enabled", "0") == "1",
        "interval": int(_get_setting("antiban_interval", "30")),
        "country": _get_setting("antiban_country", antiban.DEFAULT_COUNTRY),
        "min_pool": int(_get_setting("antiban_min_pool", "20")),
        "fresh_window_min": _fresh_window_min(),
        "running": _antiban_state["running"],
        "last_run": _antiban_state["last_run"],
        "last_result": _antiban_state["last_result"],
    }


@app.post("/api/antiban/scheduler")
async def antiban_scheduler_set(payload: dict, _: bool = Depends(require_admin)):
    if "enabled" in payload:
        _set_setting("antiban_enabled", "1" if payload["enabled"] else "0")
    if "interval" in payload:
        _set_setting("antiban_interval", max(1, int(payload["interval"])))
    if "country" in payload:
        _set_setting("antiban_country", str(payload["country"]).upper()[:2] or antiban.DEFAULT_COUNTRY)
    if "min_pool" in payload:
        _set_setting("antiban_min_pool", max(1, int(payload["min_pool"])))
    if "fresh_window_min" in payload:
        _set_setting("fresh_window_min", max(1, int(payload["fresh_window_min"])))
    _ensure_antiban_scheduler()
    return await antiban_scheduler_status()


# ══════════════════════════════════════════════════════════════
#   API KEYS (panel admin — protégelo antes de exponer en producción)
# ══════════════════════════════════════════════════════════════
@app.get("/api/keys")
async def keys_list(_: bool = Depends(require_admin)):
    with _db() as c:
        rows = c.execute("SELECT * FROM api_keys ORDER BY created_at DESC").fetchall()
    return {"keys": [dict(r) for r in rows], "admin_required": bool(ADMIN_TOKEN)}


@app.post("/api/keys")
async def keys_create(payload: dict = None, _: bool = Depends(require_admin)):
    label = (payload or {}).get("label", "").strip() or "sin nombre"
    rate_limit = int((payload or {}).get("rate_limit", 0) or 0)
    new_key = "pck_" + secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc).isoformat()
    with _db() as c:
        c.execute("INSERT INTO api_keys (key, label, rate_limit, created_at) VALUES (?,?,?,?)",
                  (new_key, label, rate_limit, now))
    return {"ok": True, "key": new_key, "label": label, "rate_limit": rate_limit}


@app.delete("/api/keys/{kid}")
async def keys_delete(kid: int, _: bool = Depends(require_admin)):
    with _db() as c:
        c.execute("DELETE FROM api_keys WHERE id=?", (kid,))
    return {"ok": True}


@app.post("/api/keys/{kid}/toggle")
async def keys_toggle(kid: int, _: bool = Depends(require_admin)):
    with _db() as c:
        row = c.execute("SELECT active FROM api_keys WHERE id=?", (kid,)).fetchone()
        if not row:
            raise HTTPException(404, "Key no encontrada")
        new = 0 if row["active"] else 1
        c.execute("UPDATE api_keys SET active=? WHERE id=?", (new, kid))
    return {"ok": True, "active": new}


# ══════════════════════════════════════════════════════════════
#   BILLING — venta de acceso a Proxies Vivas (MercadoPago)
# ══════════════════════════════════════════════════════════════
# El cliente elige un plan -> paga en MercadoPago (suscripcion mensual) ->
# se le crea una API key con el rate_limit del plan. La activacion se hace por
# CONSULTA (pull) a MercadoPago desde /api/billing/status, asi no requiere un
# webhook publico HTTPS (el servicio corre en :8200 sin dominio).
PROXY_PLANS = [
    {"id": "starter", "name": "Starter", "price": 0, "currency": "PEN",
     "rate_limit": 200, "features": ["200 proxies/día", "Geo LATAM", "Prueba gratis"]},
    {"id": "pro", "name": "Pro", "price": 39, "currency": "PEN",
     "rate_limit": 10000, "features": ["10,000 proxies/día", "Geo-priorización", "Soporte"]},
    {"id": "business", "name": "Business", "price": 99, "currency": "PEN",
     "rate_limit": 0, "features": ["Ilimitado", "Anti-ban pool", "Prioridad"]},
]
_PROXY_PLAN_BY_ID = {p["id"]: p for p in PROXY_PLANS}


def _init_billing():
    with _db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                ref TEXT PRIMARY KEY, email TEXT, plan TEXT,
                status TEXT DEFAULT 'pending', mp_preapproval_id TEXT,
                api_key TEXT, created_at TEXT, updated_at TEXT
            )
        """)


_init_billing()


def _mp_token():
    return os.getenv("MP_ACCESS_TOKEN")


def _mp_api(path, method="GET", body=None, retries=4):
    """Llama a MercadoPago. El endpoint de preapproval devuelve 500 transitorios
    a menudo, así que reintentamos ante 5xx con backoff corto."""
    import time as _t
    token = _mp_token()
    if not token:
        raise HTTPException(503, "MP_ACCESS_TOKEN no configurado")
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"https://api.mercadopago.com{path}", data=data, method=method,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if 500 <= e.code < 600 and attempt < retries - 1:
                _t.sleep(1.0 + attempt)   # backoff: 1s, 2s, 3s
                continue
            raise
        except Exception as e:
            last = e
            if attempt < retries - 1:
                _t.sleep(1.0 + attempt)
                continue
            raise
    if last:
        raise last


def _issue_api_key(email, plan) -> str:
    """Crea una API key con el rate_limit del plan y la devuelve."""
    new_key = "pck_" + secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc).isoformat()
    with _db() as c:
        c.execute("INSERT INTO api_keys (key, label, rate_limit, created_at) VALUES (?,?,?,?)",
                  (new_key, f"{email} ({plan['id']})", int(plan["rate_limit"]), now))
    return new_key


def _activate_sub(ref, mp_id=None):
    """Idempotente: crea la API key de una suscripcion pagada."""
    with _db() as c:
        row = c.execute("SELECT * FROM subscriptions WHERE ref=?", (ref,)).fetchone()
        if not row:
            return None
        if row["status"] == "active" and row["api_key"]:
            return dict(row)
        plan = _PROXY_PLAN_BY_ID.get(row["plan"])
        if not plan:
            return None
        key = _issue_api_key(row["email"], plan)
        c.execute("UPDATE subscriptions SET status='active', api_key=?, mp_preapproval_id=?,"
                  " updated_at=? WHERE ref=?", (key, mp_id, datetime.now(timezone.utc).isoformat(), ref))
        return {"ref": ref, "api_key": key, "plan": plan["id"], "status": "active"}


@app.get("/api/billing/plans")
async def billing_plans():
    return {"plans": PROXY_PLANS, "currency": "PEN"}


@app.post("/api/billing/subscribe")
async def billing_subscribe(payload: dict):
    plan = _PROXY_PLAN_BY_ID.get((payload or {}).get("plan"))
    if not plan:
        raise HTTPException(400, "plan desconocido")
    email = ((payload or {}).get("email") or "").strip().lower()
    if "@" not in email:
        raise HTTPException(400, "email invalido")
    ref = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    with _db() as c:
        c.execute("INSERT INTO subscriptions (ref, email, plan, status, created_at, updated_at)"
                  " VALUES (?,?,?,?,?,?)", (ref, email, plan["id"], "pending", now, now))

    if float(plan["price"]) <= 0:
        act = _activate_sub(ref)
        return {"mode": "free", "ref": ref, "status": "active",
                "api_key": act.get("api_key") if act else None, "plan": plan["id"]}

    if not _mp_token():
        return {"mode": "demo", "ref": ref, "plan": plan["id"], "amount": plan["price"],
                "currency": plan["currency"], "init_point": None,
                "message": "MercadoPago en DEMO: define MP_ACCESS_TOKEN."}

    base = os.getenv("PROXY_PUBLIC_URL", "http://134.122.0.220:8200")
    pre = {
        "reason": f"ELEKA Proxies {plan['name']} (mensual)",
        "external_reference": ref, "payer_email": email,
        "back_url": f"{base}/#/gracias?ref={ref}",
        "auto_recurring": {"frequency": 1, "frequency_type": "months",
                           "transaction_amount": float(plan["price"]),
                           "currency_id": plan["currency"]},
        "status": "pending",
    }
    try:
        resp = _mp_api("/preapproval", "POST", pre)
    except Exception as e:
        raise HTTPException(502, f"Error MercadoPago: {e}")
    with _db() as c:
        c.execute("UPDATE subscriptions SET mp_preapproval_id=?, updated_at=? WHERE ref=?",
                  (resp.get("id"), datetime.now(timezone.utc).isoformat(), ref))
    return {"mode": "live", "ref": ref, "plan": plan["id"],
            "preapproval_id": resp.get("id"), "init_point": resp.get("init_point")}


@app.get("/api/billing/status")
async def billing_status(ref: str):
    """Consulta el estado; si MercadoPago ya autorizo la suscripcion, crea la
    API key (modelo pull: no necesita webhook publico)."""
    with _db() as c:
        row = c.execute("SELECT ref, plan, status, api_key, mp_preapproval_id FROM subscriptions WHERE ref=?",
                        (ref,)).fetchone()
    if not row:
        raise HTTPException(404, "ref no encontrado")
    d = dict(row)
    if d["status"] != "active" and d.get("mp_preapproval_id") and _mp_token():
        try:
            pre = _mp_api(f"/preapproval/{d['mp_preapproval_id']}")
            if pre.get("status") == "authorized":
                act = _activate_sub(ref, mp_id=d["mp_preapproval_id"])
                if act:
                    d.update(status="active", api_key=act["api_key"])
        except Exception:
            pass
    return d


@app.post("/api/billing/webhook")
async def billing_webhook(payload: dict):
    """Opcional: si MercadoPago alcanza el webhook, activa al instante."""
    try:
        data_id = (payload.get("data") or {}).get("id") or payload.get("id")
        if "preapproval" in str(payload.get("type") or payload.get("topic") or "") and data_id:
            pre = _mp_api(f"/preapproval/{data_id}")
            if pre.get("status") == "authorized" and pre.get("external_reference"):
                _activate_sub(pre["external_reference"], mp_id=str(data_id))
    except Exception:
        pass
    return {"received": True}


@app.websocket("/api/ws/check")
async def ws_check(ws: WebSocket):
    await ws.accept()
    # Reset stop flag for this run
    engine._STOP_REQUESTED = False
    try:
        params = await ws.receive_json()
        source = params.get("source", "all")
        tests = params.get("tests", "hq")
        concurrency = int(params.get("concurrency", 500))
        limit = int(params.get("limit", 0))
        pasted = params.get("pasted", "")
        custom_url = params.get("custom_url", "")

        await ws.send_json({"type": "status", "msg": "Obteniendo proxies..."})

        proxies = await fetch_proxies(source, pasted)
        if not proxies:
            await ws.send_json({"type": "error", "msg": "No se obtuvieron proxies de esa fuente"})
            await ws.close()
            return

        # Limitar (muestra aleatoria)
        if limit and limit < len(proxies):
            import random
            items = list(proxies.items())
            random.shuffle(items)
            proxies = dict(items[:limit])

        engine.Config.MAX_CONCURRENT = max(50, min(concurrency, 2000))
        targets = resolve_targets(tests, custom_url)

        await ws.send_json({
            "type": "started",
            "total": len(proxies),
            "targets": targets or ["solo vida"],
            "concurrency": engine.Config.MAX_CONCURRENT,
        })

        stats = engine.Stats()
        checker = engine.ProxyChecker(stats, test_targets=targets)
        task = asyncio.create_task(checker.check_all(proxies))

        last_sent = 0
        # Escuchar mensajes de "stop" en paralelo
        async def listen_stop():
            try:
                while True:
                    msg = await ws.receive_json()
                    if msg.get("action") == "stop":
                        engine._STOP_REQUESTED = True
                        return
            except Exception:
                return
        stop_listener = asyncio.create_task(listen_stop())

        while not task.done():
            await asyncio.sleep(0.4)
            new = checker.results[last_sent:]
            last_sent = len(checker.results)
            await ws.send_json({
                "type": "progress",
                "checked": stats.checked,
                "alive": stats.alive,
                "dead": stats.dead,
                "total": stats.total,
                "speed": round(stats.speed, 1),
                "premium": stats.premium,
                "high": stats.high,
                "new": [r.to_dict() for r in new],
            })

        await task
        stop_listener.cancel()

        # Enviar lo que falte + resumen final
        new = checker.results[last_sent:]
        results = checker.results
        pool = engine.ProxyPool(results) if results else None
        summary = pool.summary if pool else {}

        await ws.send_json({
            "type": "done",
            "checked": stats.checked,
            "alive": stats.alive,
            "dead": stats.dead,
            "total": stats.total,
            "elapsed": round(stats.elapsed, 1),
            "new": [r.to_dict() for r in new],
            "summary": summary,
            "stopped": engine._STOP_REQUESTED,
        })
    except WebSocketDisconnect:
        engine._STOP_REQUESTED = True
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await ws.send_json({"type": "error", "msg": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ── Servir el frontend compilado (si existe) ──
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
