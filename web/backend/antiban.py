"""
Anti-Ban Pool - Selección de proxies geo-cercanos
==================================================
Lógica PURA (sin red, sin DB) para elegir proxies estables y cercanos al
país de la cuenta, pensada para automatizar Facebook sin disparar baneos.

Idea: cada cuenta debe usar SIEMPRE el mismo proxy (sticky), del mismo país
o de un vecino cercano, con buena latencia y anonimato. Este módulo solo se
encarga de FILTRAR y ORDENAR una lista de proxies ya verificados (dicts del
baúl). El fetch/verify y la persistencia viven en main.py.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone

# ── Orden de cercanía geográfica en Sudamérica ──
# El primer país objetivo siempre va de primero (rank 0). El resto sigue este
# orden de cercanía aproximada partiendo desde Perú (default del negocio).
# Para PE el orden resultante es exactamente: PE, EC, CO, BO, CL, BR, VE, AR, PY, UY.
SA_PROXIMITY_ORDER: List[str] = [
    "PE", "EC", "CO", "BO", "CL", "BR", "VE", "AR", "PY", "UY",
]

# País objetivo por defecto (negocio peruano).
DEFAULT_COUNTRY = "PE"

# Valor de "lejanía" para países que no están en la lista de cercanía.
# Se ordenan después de todos los vecinos conocidos.
_FAR_RANK = 999


def build_proximity_order(country: str) -> List[str]:
    """
    Construye la lista de cercanía para un país objetivo.

    El país objetivo va primero (rank 0); luego los vecinos sudamericanos
    en el orden definido en SA_PROXIMITY_ORDER (excluyendo al objetivo para
    no duplicarlo).
    """
    target = (country or DEFAULT_COUNTRY).upper()
    rest = [c for c in SA_PROXIMITY_ORDER if c != target]
    return [target] + rest


def country_rank(country: str, order: List[str]) -> int:
    """
    Devuelve el índice de cercanía de 'country' dentro de 'order'.
    Países desconocidos o fuera de la región reciben _FAR_RANK (van al final).
    """
    cc = (country or "").upper()
    try:
        return order.index(cc)
    except ValueError:
        return _FAR_RANK


def _anon_is_elite(anon_level: str) -> bool:
    """True si el proxy es de anonimato elite (preferido para anti-ban)."""
    return (anon_level or "").lower() == "elite"


def select_antiban(
    rows: List[Dict],
    country: str = DEFAULT_COUNTRY,
    min_score: int = 50,
    max_latency: float = 3000.0,
    protocol: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict]:
    """
    Filtra y ordena proxies para uso anti-ban.

    Filtros (un proxy debe cumplir TODOS):
      - vivo: en el baúl solo viven proxies vivas, pero si llega un campo
        'alive' explícito en False, se descarta.
      - score >= min_score
      - latency_ms <= max_latency (proxies sin latencia válida se descartan)
      - protocolo == protocol (si se especifica)

    Orden (de mejor a peor), por prioridad:
      1. cercanía de país (mismo país primero, luego vecinos)
      2. anonimato elite primero (preferido, no obligatorio)
      3. mayor score
      4. menor latencia

    Args:
        rows: lista de dicts del baúl (claves: address, protocol, score,
              anon_level, country, latency_ms, ...).
        country: país objetivo (ISO-2, ej "PE").
        min_score: score mínimo aceptable.
        max_latency: latencia máxima en ms.
        protocol: filtra por protocolo exacto ("http", "socks5", ...) o None.
        limit: corta la lista a N candidatos (None = todos).

    Returns:
        Lista de dicts ordenada; el primero es el MEJOR candidato anti-ban.
    """
    order = build_proximity_order(country)
    proto = (protocol or "").lower().strip() or None

    candidatos: List[Dict] = []
    for r in rows:
        # Descartar muertos explícitos (el baúl normalmente solo guarda vivos).
        if r.get("alive") is False:
            continue

        # Score mínimo.
        try:
            score = int(r.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        if score < min_score:
            continue

        # Latencia válida y dentro del máximo.
        try:
            latency = float(r.get("latency_ms", 0) or 0)
        except (TypeError, ValueError):
            latency = 0.0
        if latency <= 0 or latency > max_latency:
            continue

        # Protocolo (si se pidió uno concreto).
        if proto and (r.get("protocol", "") or "").lower() != proto:
            continue

        candidatos.append(r)

    # Orden compuesto: cercanía ASC, elite primero, score DESC, latencia ASC.
    def _sort_key(r: Dict):
        rank = country_rank(r.get("country", ""), order)
        elite_first = 0 if _anon_is_elite(r.get("anon_level", "")) else 1
        try:
            score = int(r.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        try:
            latency = float(r.get("latency_ms", 0) or 0)
        except (TypeError, ValueError):
            latency = 0.0
        return (rank, elite_first, -score, latency)

    candidatos.sort(key=_sort_key)

    if limit and limit > 0:
        candidatos = candidatos[:limit]
    return candidatos


def best_antiban(rows: List[Dict], **kwargs) -> Optional[Dict]:
    """Atajo: devuelve el MEJOR candidato anti-ban (o None si no hay)."""
    sel = select_antiban(rows, **kwargs)
    return sel[0] if sel else None


# ══════════════════════════════════════════════════════════════
#   FRESCURA Y MÉTRICAS DEL POOL (lógica PURA, testeable sin DB)
# ══════════════════════════════════════════════════════════════
# El producto vende proxies "vivas y verificadas HACE POCO". Estas funciones
# solo razonan sobre la marca de tiempo `last_check` (ISO-8601) de cada fila
# del baúl; el guardado y la verificación viven en main.py.

# Ventana de frescura por defecto: una proxy se considera "fresca" si fue
# verificada dentro de los últimos N minutos.
FRESH_WINDOW_MIN_DEFAULT = 30


def _parse_ts(value) -> Optional[datetime]:
    """Parsea un timestamp ISO-8601 a datetime tz-aware (UTC). None si inválido."""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def is_fresh(last_check, window_min: int = FRESH_WINDOW_MIN_DEFAULT, now=None) -> bool:
    """
    True si `last_check` (ISO-8601) cae dentro de la ventana de frescura.

    Args:
        last_check: timestamp ISO de la última verificación (str) o None.
        window_min: ventana de frescura en minutos.
        now: datetime de referencia (default: ahora UTC). Útil para tests.
    """
    ts = _parse_ts(last_check)
    if ts is None:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_min = (now - ts).total_seconds() / 60.0
    # Toleramos timestamps levemente futuros (reloj desincronizado) y exigimos
    # que la edad no supere la ventana configurada.
    return age_min <= window_min and age_min >= -1.0


def filter_fresh(
    rows: List[Dict],
    window_min: int = FRESH_WINDOW_MIN_DEFAULT,
    now=None,
    field: str = "last_check",
) -> List[Dict]:
    """Devuelve solo las filas cuya `last_check` está dentro de la ventana."""
    return [r for r in rows if is_fresh(r.get(field), window_min, now)]


def compute_pool_stats(
    rows: List[Dict],
    fresh_window_min: int = FRESH_WINDOW_MIN_DEFAULT,
    now=None,
) -> Dict:
    """
    Calcula métricas de confianza del pool sobre las proxies FRESCAS.

    'alive_now' = nº de proxies verificadas dentro de la ventana de frescura
    (en el baúl solo viven proxies vivas, así que fresco == vivo y confiable).

    Returns dict con: alive_now, by_country, avg_latency_ms, avg_score,
    fresh_window_min.
    """
    fresh = filter_fresh(rows, fresh_window_min, now)
    by_country: Dict[str, int] = {}
    lat_sum = 0.0
    lat_n = 0
    score_sum = 0
    score_n = 0
    for r in fresh:
        cc = (r.get("country") or "??").upper()
        by_country[cc] = by_country.get(cc, 0) + 1
        try:
            lat = float(r.get("latency_ms") or 0)
        except (TypeError, ValueError):
            lat = 0.0
        if lat > 0:
            lat_sum += lat
            lat_n += 1
        try:
            score_sum += int(r.get("score") or 0)
            score_n += 1
        except (TypeError, ValueError):
            pass
    return {
        "alive_now": len(fresh),
        "by_country": dict(sorted(by_country.items(), key=lambda kv: -kv[1])),
        "avg_latency_ms": round(lat_sum / lat_n, 1) if lat_n else 0.0,
        "avg_score": round(score_sum / score_n, 1) if score_n else 0.0,
        "fresh_window_min": fresh_window_min,
    }
