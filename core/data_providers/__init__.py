"""
Cadena de proveedores con fallback: yfinance primero, Alpha Vantage si falla.
El resto de la app llama a estas funciones y no le importa de dónde vino el dato.
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from config.settings import settings
from core.data_providers.alpha_vantage_client import AlphaVantageProvider
from core.data_providers.yfinance_client import YFinanceProvider

logger = logging.getLogger(__name__)

_primary = YFinanceProvider()
_fallback = AlphaVantageProvider()

_price_cache: dict[str, tuple[float, float]] = {}  # ticker -> (precio, timestamp)
# (ticker, period) -> (DataFrame, timestamp). Sin esto, cada rerun de Streamlit
# (cualquier clic) volvía a bajar 2 años de historia de cada posición.
_history_cache: dict[tuple[str, str], tuple[pd.DataFrame, float]] = {}


def get_price(ticker: str, use_cache: bool = True) -> float | None:
    now = time.time()
    if use_cache and ticker in _price_cache:
        precio, ts = _price_cache[ticker]
        if now - ts < settings.PRICE_CACHE_TTL_SECONDS:
            return precio

    precio = _primary.get_price(ticker)
    fuente = _primary.name
    if precio is None:
        precio = _fallback.get_price(ticker)
        fuente = _fallback.name

    if precio is not None:
        _price_cache[ticker] = (precio, now)
        logger.debug("Precio de %s: %s (fuente: %s)", ticker, precio, fuente)
    else:
        logger.warning("No se pudo obtener precio de %s en ningún proveedor.", ticker)
    return precio


def get_history(ticker: str, period: str | None = None, use_cache: bool = True) -> pd.DataFrame | None:
    period = period or settings.HISTORY_PERIOD
    clave = (ticker, period)
    now = time.time()
    if use_cache and clave in _history_cache:
        hist, ts = _history_cache[clave]
        if now - ts < settings.PRICE_CACHE_TTL_SECONDS:
            return hist.copy()

    hist = _primary.get_history(ticker, period=period)
    if hist is None or hist.empty:
        logger.info("yfinance sin histórico para %s, probando Alpha Vantage...", ticker)
        hist = _fallback.get_history(ticker, period=period)

    if hist is not None and not hist.empty:
        _history_cache[clave] = (hist, now)
        return hist.copy()
    return hist


def limpiar_cache() -> None:
    """Vacía los caches en memoria de precios e históricos."""
    _price_cache.clear()
    _history_cache.clear()


def get_info(ticker: str) -> dict:
    info = _primary.get_info(ticker)
    if info:
        return info
    return _fallback.get_info(ticker)


def get_history_multi(tickers: list[str], period: str | None = None) -> pd.DataFrame:
    """Combina históricos de varios tickers en un solo DataFrame alineado por fecha."""
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
