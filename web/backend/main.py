"""
Proxy Checker Pro - Web Backend (FastAPI + WebSocket)
=====================================================
Envuelve el motor async `proxy_checker_v2` y transmite el progreso
de verificación en vivo por WebSocket.
"""

import os
import re
import sys
import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ── Importar el motor (raíz del repo) ──
ENGINE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ENGINE_DIR))
import proxy_checker_v2 as engine  # noqa: E402

app = FastAPI(title="Proxy Checker Pro - Web", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


init_vault()


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
async def vault_clear():
    with _db() as c:
        c.execute("DELETE FROM vault")
    return {"ok": True, "total": 0}


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
