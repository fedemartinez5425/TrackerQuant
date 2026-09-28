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


def get_history(ticker: str, period: str | None = None) -> pd.DataFrame | None:
    period = period or settings.HISTORY_PERIOD
    hist = _primary.get_history(ticker, period=period)
    if hist is not None and not hist.empty:
        return hist
    logger.info("yfinance sin histórico para %s, probando Alpha Vantage...", ticker)
    return _fallback.get_history(ticker, period=period)


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
    combined = pd.concat(frames, axis=1)
    combined = combined.ffill().dropna(how="all")
    return combined
