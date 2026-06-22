"""
Proxy Checker Pro - Web Backend (FastAPI + WebSocket)
=====================================================
Envuelve el motor async `proxy_checker_v2` y transmite el progreso
de verificación en vivo por WebSocket.
"""

import os
import re
import sys
import secrets
import asyncio
import sqlite3
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
                c.execute(
                    "INSERT OR IGNORE INTO vault (address, protocol, score, quality, anon_level, country, latency_ms, note, saved_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (addr, p.get("protocol", ""), int(p.get("score", 0) or 0), p.get("quality", ""),
                     p.get("anon_level", ""), p.get("country", ""), float(p.get("latency_ms", 0) or 0),
                     p.get("note", ""), now),
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
                c.execute(
                    "INSERT OR IGNORE INTO vault (address, protocol, score, quality, anon_level, country, latency_ms, note, saved_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (d["address"], d["protocol"], d["score"], d["quality"], d["anon_level"],
                     d["country"], d["latency_ms"], "auto", now),
                )
                if c.total_changes:
                    added += 1
            except Exception:
                continue
    return {"ok": True, "checked": stats.checked, "alive": stats.alive, "added": added, "total": len(_vault_rows())}


@app.post("/api/vault/refresh")
async def vault_refresh(payload: dict = None, _: bool = Depends(require_admin)):
    payload = payload or {}
    return await _do_refresh(int(payload.get("limit", 600)))


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
                if _get_setting("sched_verify", "1") == "1":
                    await _do_verify(prune=True)
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
    _ensure_scheduler()


@app.get("/api/scheduler")
async def scheduler_status():
    return {
        "enabled": _get_setting("sched_enabled", "0") == "1",
        "interval": int(_get_setting("sched_interval", "30")),
        "limit": int(_get_setting("sched_limit", "600")),
        "verify": _get_setting("sched_verify", "1") == "1",
        "running": _scheduler_state["running"],
        "last_run": _scheduler_state["last_run"],
        "last_result": _scheduler_state["last_result"],
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
    _ensure_scheduler()
    return await scheduler_status()


# ══════════════════════════════════════════════════════════════
#   ROTADOR EN VIVO (gated por API key) — para vender acceso
# ══════════════════════════════════════════════════════════════
@app.get("/api/proxy")
async def rotate_proxy(
    protocol: str = Query(None),
    min_score: int = Query(0),
    country: str = Query(None),
    format: str = Query("json"),
    keyrow: dict = Depends(require_key),
):
    """Devuelve el SIGUIENTE proxy del baúl (round-robin) según filtros. Requiere API key."""
    rows = _vault_rows()
    rows = [r for r in rows if r["score"] >= min_score]
    if protocol:
        rows = [r for r in rows if r["protocol"] == protocol]
    if country:
        rows = [r for r in rows if r["country"] == country]
    if not rows:
        raise HTTPException(404, "No hay proxies en el baúl que cumplan el filtro")

    sig = f"{protocol}|{min_score}|{country}"
    i = _rot_idx.get(sig, 0)
    proxy = rows[i % len(rows)]
    _rot_idx[sig] = (i + 1) % len(rows)

    if format == "text":
        return PlainTextResponse(f"{proxy['protocol']}://{proxy['address']}")
    return {
        "proxy": f"{proxy['protocol']}://{proxy['address']}",
        "address": proxy["address"], "protocol": proxy["protocol"],
        "score": proxy["score"], "quality": proxy["quality"],
        "anon_level": proxy["anon_level"], "country": proxy["country"],
        "latency_ms": proxy["latency_ms"], "pool_size": len(rows),
    }


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
