"""
Antes esto se cargaba a mano (o vía bonos AL30/AL30D en Google Sheets).
Ahora se calcula 100% automático con yfinance: se toma un CEDEAR muy líquido
que cotiza tanto en BCBA (en pesos) como su ADR en EEUU (en dólares), y se
despeja el tipo de cambio implícito:

    CCL = (precio_CEDEAR_ARS * ratio) / precio_ADR_USD

Se prueba una lista de pares en orden (settings.CCL_PARES) por si el
primero no tiene datos ese día (ticker desactualizado, feriado, etc.).

IMPORTANTE: los ratios de conversión de CEDEARs pueden cambiar con el
tiempo (ampliaciones de capital, splits, etc.). Los valores en
settings.CCL_PARES son una referencia razonable pero conviene
confirmarlos de tanto en tanto contra una fuente como BYMA o el propio
broker, y ajustarlos en config/settings.py si hace falta.
"""
from __future__ import annotations

import logging
import time

from config.settings import settings
from core import data_providers

logger = logging.getLogger(__name__)

_ccl_cache: tuple[float, float] | None = None  # (valor, timestamp)


def _calcular_ccl_par(ticker_ars: str, ticker_usd: str, ratio: float) -> float | None:
    precio_ars = data_providers.get_price(ticker_ars)
    precio_usd = data_providers.get_price(ticker_usd)
    if not precio_ars or not precio_usd:
        return None
    return (precio_ars * ratio) / precio_usd


def get_ccl_automatico(use_cache: bool = True) -> dict | None:
    """Devuelve {'valor': float, 'fuente': 'TICKER_ARS/TICKER_USD'} o None si
    ningún par configurado tiene datos disponibles en este momento."""
    global _ccl_cache
    now = time.time()
    if use_cache and _ccl_cache and (now - _ccl_cache[1] < settings.PRICE_CACHE_TTL_SECONDS):
        return {"valor": _ccl_cache[0], "fuente": "cache"}

    for ticker_ars, ticker_usd, ratio in settings.CCL_PARES:
        ccl = _calcular_ccl_par(ticker_ars, ticker_usd, ratio)
        if ccl:
            _ccl_cache = (ccl, now)
            fuente = f"{ticker_ars}/{ticker_usd} (ratio {ratio:g}:1)"
            logger.info("CCL calculado automáticamente vía %s: %.2f", fuente, ccl)
            return {"valor": ccl, "fuente": fuente}

    logger.warning("No se pudo calcular el CCL automáticamente con ningún par configurado.")
    return None


def get_ccl_historico(period: str | None = None):
    """Serie histórica diaria de CCL, calculada con el mismo par usado hoy
    (el primero de settings.CCL_PARES que tenga histórico disponible).
    Necesaria para convertir precios de acciones argentinas directas a
    dólares equivalentes en toda la ventana histórica -- no solo hoy --
    y así poder mezclarlas de forma coherente con las CEDEAR (que ya
    vienen en USD vía su ADR) en los cálculos de riesgo.
    """
    import pandas as pd

    period = period or settings.HISTORY_PERIOD
    for ticker_ars, ticker_usd, ratio in settings.CCL_PARES:
        hist_ars = data_providers.get_history(ticker_ars, period=period)
        hist_usd = data_providers.get_history(ticker_usd, period=period)
        if hist_ars is None or hist_usd is None or hist_ars.empty or hist_usd.empty:
            continue
        combinado = pd.concat([hist_ars, hist_usd], axis=1).ffill().dropna()
        if combinado.empty:
            continue
        ccl_serie = (combinado[ticker_ars] * ratio) / combinado[ticker_usd]
        ccl_serie.name = "CCL"
        logger.info("CCL histórico calculado vía %s/%s (%d días).", ticker_ars, ticker_usd, len(ccl_serie))
        return ccl_serie

    logger.warning("No se pudo calcular el CCL histórico con ningún par configurado.")
    return None
