"""
Cadena de proveedores con fallback: yfinance primero, Alpha Vantage si falla.
El resto de la app llama a estas funciones y no le importa de dónde vino el dato.

Robustez (Yahoo limita las IPs compartidas de Streamlit Cloud):
- Una sola historia por ticker en memoria: se baja la ventana más larga
  (`settings.HISTORY_PERIOD_BASE`, 3 años) y los pedidos de 1 o 2 años se
  recortan de ahí. Antes se bajaba todo dos veces (2y para riesgo, 3y para decisión).
- `precargar()` baja en UNA request todo lo que falte (yf.download).
- Cortacircuito: tras varias fallas seguidas (o un rate limit) se deja de
  llamar a Yahoo por unos minutos y se usa lo que haya en memoria, en vez de
  encadenar timeouts y dejar la página colgada.
- Almacén (core/data_providers/almacen.py): si el ETL diario ya guardó la
  historia de un ticker, se usa esa y a Yahoo solo se le piden los últimos
  días (los posteriores al último cierre guardado). Si Yahoo no responde,
  alcanza con el almacén.
"""
from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict

import pandas as pd

from config.settings import settings
from core.data_providers import almacen
from core.data_providers.alpha_vantage_client import AlphaVantageProvider
from core.data_providers.yfinance_client import YFinanceProvider

logger = logging.getLogger(__name__)

_primary = YFinanceProvider()
_fallback = AlphaVantageProvider()

MAX_TICKERS_EN_MEMORIA = 300
# Lo que se le pide a Yahoo para completar el almacén (cubre un fin de semana
# largo + feriados: solo se agregan los días posteriores al último cierre guardado).
PERIODO_COMPLETAR = "10d"  # tope del cache: en Cloud hay ~1 GB de RAM compartida

_price_cache: dict[str, tuple[float, float]] = {}  # ticker -> (precio, timestamp)
# ticker -> (DataFrame, timestamp, días cubiertos). Sin esto, cada rerun de
# Streamlit (cualquier clic) volvía a bajar años de historia de cada posición.
_history_cache: OrderedDict[str, tuple[pd.DataFrame, float, float]] = OrderedDict()

# ---------------- Cortacircuito ----------------
FALLAS_PARA_CORTAR = 3
PAUSA_FALLAS_SEGUNDOS = 120
PAUSA_RATE_LIMIT_SEGUNDOS = 300

_fallas_seguidas = 0
_cortado_hasta = 0.0
_ultimo_exito: float | None = None
_ultimo_error: str | None = None


def _yahoo_disponible() -> bool:
    return time.time() >= _cortado_hasta


def _registrar_resultado() -> None:
    """Actualiza el cortacircuito según el último error del proveedor primario."""
    global _fallas_seguidas, _cortado_hasta, _ultimo_exito, _ultimo_error
    error = _primary.ultimo_error
    if error is None:
        _fallas_seguidas = 0
        _ultimo_exito = time.time()
        return
    _fallas_seguidas += 1
    _ultimo_error = f"{type(error).__name__}: {error}"[:300]
    if _primary.rate_limit:
        _cortado_hasta = time.time() + PAUSA_RATE_LIMIT_SEGUNDOS
        logger.warning("Yahoo limitó las requests (rate limit): pausa de %d s.", PAUSA_RATE_LIMIT_SEGUNDOS)
    elif _fallas_seguidas >= FALLAS_PARA_CORTAR:
        _cortado_hasta = time.time() + PAUSA_FALLAS_SEGUNDOS
        logger.warning("Yahoo falló %d veces seguidas: pausa de %d s.", _fallas_seguidas, PAUSA_FALLAS_SEGUNDOS)


def estado_proveedores() -> dict:
    """Para la página Estado del sistema."""
    restante = max(0.0, _cortado_hasta - time.time())
    return {
        "yahoo_disponible": restante == 0,
        "pausa_restante_segundos": int(restante),
        "fallas_seguidas": _fallas_seguidas,
        "ultimo_exito": _ultimo_exito,
        "ultimo_error": _ultimo_error,
        "tickers_en_memoria": len(_history_cache),
        "alpha_vantage_configurado": bool(settings.ALPHA_VANTAGE_API_KEY),
        "almacen": almacen.estado(),
    }


# ---------------- Períodos ----------------
_UNIDADES_DIAS = {"d": 1, "wk": 7, "mo": 30.4375, "y": 365.25}


def dias_periodo(period: str) -> float:
    """'2y' -> 730,5; '6mo' -> 182,6; 'max' (o desconocido) -> infinito."""
    m = re.fullmatch(r"(\d+)(d|wk|mo|y)", period.strip())
    if not m:
        return float("inf")
    return int(m.group(1)) * _UNIDADES_DIAS[m.group(2)]


def _periodo_a_bajar(period: str) -> str:
    """Se baja siempre al menos la ventana base, así un pedido de 2y y uno
    de 3y comparten la misma descarga."""
    base = settings.HISTORY_PERIOD_BASE
    return period if dias_periodo(period) > dias_periodo(base) else base


def _recortar(hist: pd.DataFrame, period: str) -> pd.DataFrame:
    dias = dias_periodo(period)
    if dias == float("inf") or hist.empty:
        return hist.copy()
    desde = pd.Timestamp.today().normalize() - pd.Timedelta(days=dias)
    return hist.loc[hist.index >= desde].copy()


def _guardar_historia(ticker: str, hist: pd.DataFrame, dias_cubiertos: float) -> None:
    _history_cache[ticker] = (hist, time.time(), dias_cubiertos)
    _history_cache.move_to_end(ticker)
    while len(_history_cache) > MAX_TICKERS_EN_MEMORIA:
        _history_cache.popitem(last=False)


def _completar_con_vivo(base: pd.DataFrame, vivo: pd.DataFrame | None, ticker: str) -> pd.DataFrame:
    """Agrega a la historia del almacén solo los días POSTERIORES a su último
    cierre (no pisa el pasado: el ETL lo reescribe entero cada día)."""
    if vivo is None or vivo.empty or ticker not in vivo.columns:
        return base
    nuevos = vivo.loc[vivo.index > base.index.max(), [ticker]].dropna()
    return pd.concat([base, nuevos]) if not nuevos.empty else base


def _desde_almacen(ticker: str, period: str) -> float | None:
    """Días que cubre el almacén para este ticker (None si no lo cubre)."""
    base = almacen.serie(ticker, period)
    if base is None:
        return None
    return (pd.Timestamp.today().normalize() - base.index.min()).days + almacen.MARGEN_COBERTURA_DIAS


def _historia_en_cache(ticker: str, period: str, aceptar_vencida: bool = False) -> pd.DataFrame | None:
    item = _history_cache.get(ticker)
    if not item:
        return None
    hist, ts, dias_cubiertos = item
    if dias_cubiertos < dias_periodo(period):
        return None
    if not aceptar_vencida and time.time() - ts >= settings.PRICE_CACHE_TTL_SECONDS:
        return None
    return hist


# ---------------- API pública ----------------
def get_price(ticker: str, use_cache: bool = True) -> float | None:
    now = time.time()
    if use_cache and ticker in _price_cache:
        precio, ts = _price_cache[ticker]
        if now - ts < settings.PRICE_CACHE_TTL_SECONDS:
            return precio

    # Si ya hay historia fresca en memoria, el último cierre ES el precio:
    # evita una request por ticker (antes: 2 por posición + 6 para el CCL).
    if use_cache:
        hist = _historia_en_cache(ticker, "5d")
        if hist is not None and ticker in hist.columns and hist[ticker].notna().any():
            precio = float(hist[ticker].dropna().iloc[-1])
            _price_cache[ticker] = (precio, now)
            return precio

    precio = None
    if _yahoo_disponible():
        precio = _primary.get_price(ticker)
        _registrar_resultado()
    if precio is None:
        precio = _fallback.get_price(ticker)
    if precio is None:
        # Último recurso: el último cierre conocido aunque el cache esté vencido.
        hist = _historia_en_cache(ticker, "5d", aceptar_vencida=True)
        if hist is not None and ticker in hist.columns and hist[ticker].notna().any():
            precio = float(hist[ticker].dropna().iloc[-1])

    if precio is not None:
        _price_cache[ticker] = (precio, now)
    else:
        logger.warning("No se pudo obtener precio de %s en ningún proveedor.", ticker)
    return precio


def get_history(ticker: str, period: str | None = None, use_cache: bool = True) -> pd.DataFrame | None:
    period = period or settings.HISTORY_PERIOD
    if use_cache:
        hist = _historia_en_cache(ticker, period)
        if hist is not None:
            return _recortar(hist, period)

    base = almacen.serie(ticker, period)
    if base is not None:
        vivo = None
        if _yahoo_disponible():
            vivo = _primary.get_history(ticker, period=PERIODO_COMPLETAR)
            _registrar_resultado()
        hist = _completar_con_vivo(base, vivo, ticker)
        _guardar_historia(ticker, hist, _desde_almacen(ticker, period))
        return _recortar(hist, period)

    period_bajado = _periodo_a_bajar(period)
    hist = None
    if _yahoo_disponible():
        hist = _primary.get_history(ticker, period=period_bajado)
        _registrar_resultado()
    if hist is None or hist.empty:
        logger.info("yfinance sin histórico para %s, probando Alpha Vantage...", ticker)
        hist = _fallback.get_history(ticker, period=period_bajado)

    if hist is not None and not hist.empty:
        _guardar_historia(ticker, hist, dias_periodo(period_bajado))
        return _recortar(hist, period)

    # Yahoo caído: mejor una historia de hace un rato que nada.
    vieja = _historia_en_cache(ticker, period, aceptar_vencida=True)
    if vieja is not None:
        logger.info("Usando histórico en memoria (vencido) de %s.", ticker)
        return _recortar(vieja, period)
    return hist


def precargar(tickers: list[str], period: str | None = None) -> None:
    """Baja en UNA request los históricos que no estén frescos en memoria.
    Después, get_history / get_price de esos tickers salen del cache."""
    period = period or settings.HISTORY_PERIOD
    faltantes = sorted({t for t in tickers if t and _historia_en_cache(t, period) is None})
    if not faltantes:
        return
    en_almacen = {t: almacen.serie(t, period) for t in faltantes}
    en_almacen = {t: s for t, s in en_almacen.items() if s is not None}
    a_bajar = [t for t in faltantes if t not in en_almacen]

    # Los que están en el almacén: una request chica con los últimos días.
    if en_almacen:
        vivos = {}
        if _yahoo_disponible():
            vivos = _primary.get_history_lote(sorted(en_almacen), period=PERIODO_COMPLETAR)
            _registrar_resultado()
        for ticker, base in en_almacen.items():
            _guardar_historia(ticker, _completar_con_vivo(base, vivos.get(ticker), ticker), _desde_almacen(ticker, period))

    # El resto (tickers nuevos o períodos más largos): la ventana completa.
    if a_bajar and _yahoo_disponible():
        period_bajado = _periodo_a_bajar(period)
        lote = _primary.get_history_lote(a_bajar, period=period_bajado)
        _registrar_resultado()
        for ticker, hist in lote.items():
            _guardar_historia(ticker, hist, dias_periodo(period_bajado))
        if lote:
            logger.info("Precarga en lote: %d/%d tickers.", len(lote), len(a_bajar))


def limpiar_cache() -> None:
    """Vacía los caches en memoria de precios e históricos (y fuerza a releer el almacén)."""
    _price_cache.clear()
    _history_cache.clear()
    almacen.invalidar()


def get_info(ticker: str) -> dict:
    info = _primary.get_info(ticker) if _yahoo_disponible() else {}
    if info:
        return info
    return _fallback.get_info(ticker)


def get_history_multi(tickers: list[str], period: str | None = None) -> pd.DataFrame:
    """Combina históricos de varios tickers en un solo DataFrame alineado por fecha."""
    precargar(tickers, period)
    frames = []
    for t in tickers:
        h = get_history(t, period=period)
        if h is not None and not h.empty:
            frames.append(h)
    if not frames:
        return pd.DataFrame()
    # Sin forward-fill: cada serie conserva solo sus días reales de cotización.
    # La alineación entre calendarios distintos (feriados de un mercado y no
    # del otro) se hace después, en core/portfolio/historicos.alinear_dias_comunes.
    return pd.concat(frames, axis=1).dropna(how="all")
