# 🚀 Despliegue — Proxy Checker Pro (Web)

Guía para montar la app como servicio en internet y vender acceso por API key.

## Opción A — Docker (recomendado)

Desde la **raíz del repo**:

```bash
# build + run con docker-compose
cd web
docker compose up -d --build
```

La app queda en `http://TU_SERVIDOR:8000`. El baúl y las API keys se persisten en `web/data/`.

> Edita `ADMIN_TOKEN` en `docker-compose.yml` (o pásalo con `-e`) antes de exponerlo.

### Docker manual
```bash
docker build -f web/Dockerfile -t proxy-checker-pro .
docker run -d -p 8000:8000 -e ADMIN_TOKEN="token_secreto_largo" \
  -v $(pwd)/data:/app/web/backend proxy-checker-pro
```

## Opción B — VPS sin Docker (Ubuntu)

```bash
# 1. Dependencias
sudo apt update && sudo apt install -y python3-pip nodejs npm
# 2. Backend
cd web/backend && pip install -r requirements.txt
pip install aiohttp aiohttp-socks colorama requests
# 3. Frontend (build)
cd ../frontend && npm install && npm run build
# 4. Arrancar (sirve el frontend compilado en /)
cd ../backend
ADMIN_TOKEN="token_secreto_largo" python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Para dejarlo corriendo 24/7 usa **systemd** o `pm2`/`screen`.

## 🔒 Checklist antes de exponer en internet

1. **Define `ADMIN_TOKEN`** (variable de entorno). Sin él, el panel de API Keys y el Scheduler quedan abiertos.
   - En la web, pega el token en el campo "admin token" (arriba a la derecha) para administrar.
2. **Pon un dominio + HTTPS** con Nginx + Let's Encrypt (proxy inverso a `localhost:8000`).
   - El WebSocket (`/api/ws/check`) ya funciona sobre `wss://` automáticamente.
3. **Activa el Auto-refresh** (pestaña Auto-refresh) para mantener el baúl fresco sin intervención.
4. **Crea API keys** con límite diario por cliente (pestaña API Keys).

### Nginx (proxy inverso + WebSocket)
```nginx
server {
    server_name proxies.tudominio.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

## 💰 Cómo vende acceso tu cliente
El cliente solo necesita su API key:
```bash
curl "https://proxies.tudominio.com/api/proxy?key=SU_API_KEY&protocol=socks5&min_score=60"
```
Cada petición devuelve una proxy distinta del baúl (siempre fresco gracias al Auto-refresh).
