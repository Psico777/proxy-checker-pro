# ── Etapa 1: build del frontend ──
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Etapa 2: backend + frontend compilado ──
FROM python:3.12-slim
WORKDIR /app

# Motor (raíz del repo) + backend
COPY proxy_checker_v2.py /app/proxy_checker_v2.py
COPY web/backend/ /app/web/backend/
COPY --from=frontend /app/frontend/dist /app/web/frontend/dist

RUN pip install --no-cache-dir -r /app/web/backend/requirements.txt \
    && pip install --no-cache-dir aiohttp aiohttp-socks colorama requests

WORKDIR /app/web/backend
EXPOSE 8000

# Define ADMIN_TOKEN en runtime para proteger el panel admin:
#   docker run -e ADMIN_TOKEN=tu_token_secreto -p 8000:8000 proxy-checker-pro
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
