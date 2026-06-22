<div align="center">

# 🔍 Proxy Checker Pro

### Motor asíncrono de obtención y verificación de proxies

**Descarga ~20,000 proxies de 30+ fuentes, las verifica con doble check, y te entrega solo las que funcionan — clasificadas por protocolo, calidad y país.**

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![Async](https://img.shields.io/badge/Engine-asyncio-00d4ff)
![Proxies](https://img.shields.io/badge/Soporta-HTTP%2FHTTPS%2FSOCKS4%2FSOCKS5-7c3aed)
![License](https://img.shields.io/badge/Licencia-MIT-success)

</div>

---

## ⚡ ¿Qué hace?

1. **Descarga** proxies de 30+ fuentes (APIs + repos de GitHub) en paralelo
2. **Filtra duplicados** automáticamente (IP:PORT único, validación de octetos)
3. **Doble verificación** — cada proxy se testea contra 2 URLs distintas para eliminar falsos positivos
4. **Mide latencia** promedio en milisegundos
5. **Detecta anonimato** — Elite 🛡️ / Anonymous 🔒 / Transparent 👁️
6. **Geolocaliza** cada proxy por país
7. **Prueba sitios protegidos** (Google, Cloudflare, httpbin, azenv)
8. **Puntúa** cada proxy de 0 a 100 con scoring inteligente
9. **Exporta** resultados organizados por **protocolo × calidad** (Excel/CSV/JSON/TXT)
10. **Ctrl+C seguro** — guarda todo lo encontrado al interrumpir

---

## 📦 Instalación

```bash
git clone https://github.com/Psico777/proxy-checker-pro.git
cd proxy-checker-pro
pip install -r requirements.txt
```

**Requisitos:** Python 3.9+ y conexión a internet.

## 🚀 Uso

```bash
python proxy_checker_v2.py
```

Menú interactivo: eliges fuente de proxies, nivel de tests, concurrencia (200–1200 conexiones) y control de tiempo. El checker estima cuánto tardará antes de empezar.

---

## 📊 Sistema de Scoring (0–100)

| Factor | Máx | Detalle |
|--------|-----|---------|
| Latencia | 35 | <1s = 35, <2.5s = 25, <5s = 15 |
| Anonimato | 30 | Elite = 30, Anonymous = 20, Transparent = 5 |
| Protocolo | 10 | SOCKS5 = 10, HTTPS = 8, SOCKS4 = 7, HTTP = 5 |
| Targets OK | 25 | Proporcional a % de targets superados |

**Clasificación:** ⭐ PREMIUM (≥80) · 🟢 HIGH (≥60) · 🟡 MEDIUM (≥40) · 🔴 LOW (<40)

---

## 💾 Salida organizada

Resultados en `results/YYYYMMDD_HHMMSS/`:

```
socks5_premium.txt     ★ las mejores
quality_premium.txt    todos los protocolos PREMIUM
hq_elite.txt           score≥60 + anonimato Elite
detailed_report.txt    reporte completo
proxies_full.json      JSON programático
proxies.csv            para Excel/Sheets
```

## 🔄 Uso programático (ProxyPool rotativo)

```python
from proxy_checker_v2 import ProxyPool, ProxyResult

pool = ProxyPool(results)
best   = pool.get_best(1)[0]                              # la mejor
rand   = pool.get_random(min_score=60)                   # aleatoria de calidad
rot    = pool.get_next(protocol="socks5", min_score=50)  # rotación
geo    = pool.get_next(country="US", min_score=40)        # por país
```

---

## 📡 Fuentes (30+ verificadas)

**APIs:** ProxyScrape · OpenProxyList · ProxySpace
**GitHub:** TheSpeedX · monosans · clarketm · jetkai · roosterkid · prxchk · zevtyardt · rdavydov · sunny9577 · mmpx12

---

## 🗺️ Documentación

- **[GUIA_DE_USO.md](GUIA_DE_USO.md)** — qué tipo de proxy usar para cada caso (scraping, automatización, testing) e integración con Scrapy, Selenium, curl.

---

## ⚠️ Uso Responsable

Esta herramienta verifica proxies públicas para usos **legítimos**: web scraping de datos públicos, testing geográfico, automatización y privacidad. El usuario es responsable de cumplir los términos de servicio de los sitios que visite y las leyes aplicables.

## 📜 Licencia

MIT — libre para uso personal y comercial. Ver [LICENSE](LICENSE).

---

<div align="center">

**Proxy Checker Pro** · Motor async de verificación de proxies · por [Psico777](https://github.com/Psico777)

</div>
