"""
Antes esto se cargaba a mano (o vía bonos AL30/AL30D en Google Sheets).
Ahora se calcula 100% automático con yfinance: se toman CEDEARs/acciones muy
líquidas que cotizan tanto en BCBA (en pesos) como su ADR en EEUU (en
dólares), y se despeja el tipo de cambio implícito:

    CCL = (precio_ARS * ratio) / precio_ADR_USD

Se calcula con TODOS los pares de settings.CCL_PARES que tengan datos y se
usa la MEDIANA: así un par con un precio desactualizado o un ratio mal
cargado no distorsiona el CCL (con un solo par, cualquier error pasaba
directo a toda la cartera). Si los pares difieren mucho entre sí se loguea
una advertencia.

IMPORTANTE: los ratios de conversión pueden cambiar con el tiempo
(ampliaciones de capital, splits, etc.). Los valores en settings.CCL_PARES
son una referencia razonable pero conviene confirmarlos de tanto en tanto
contra una fuente como BYMA o el propio broker.
"""
from __future__ import annotations

import logging
import statistics
import time

from config.settings import settings
from core import data_providers

logger = logging.getLogger(__name__)

_ccl_cache: tuple[float, float, str] | None = None  # (valor, timestamp, fuente)

DISPERSION_MAXIMA_ENTRE_PARES = 0.05  # 5%: por encima, se avisa en el log


def _calcular_ccl_par(ticker_ars: str, ticker_usd: str, ratio: float) -> float | None:
    precio_ars = data_providers.get_price(ticker_ars)
    precio_usd = data_providers.get_price(ticker_usd)
    if not precio_ars or not precio_usd:
        return None
    return (precio_ars * ratio) / precio_usd


def get_ccl_automatico(use_cache: bool = True) -> dict | None:
    """Devuelve {'valor': float, 'fuente': str} o None si ningún par
    configurado tiene datos disponibles en este momento."""
    global _ccl_cache
    now = time.time()
    if use_cache and _ccl_cache and (now - _ccl_cache[1] < settings.PRICE_CACHE_TTL_SECONDS):
        return {"valor": _ccl_cache[0], "fuente": _ccl_cache[2]}

    valores: list[float] = []
    pares_usados: list[str] = []
    for ticker_ars, ticker_usd, ratio in settings.CCL_PARES:
        ccl = _calcular_ccl_par(ticker_ars, ticker_usd, ratio)
        if ccl:
            valores.append(ccl)
            pares_usados.append(f"{ticker_ars}/{ticker_usd} (ratio {ratio:g}:1)")

    if not valores:
        logger.warning("No se pudo calcular el CCL automáticamente con ningún par configurado.")
        return None

    valor = float(statistics.median(valores))
    if len(valores) > 1:
        dispersion = (max(valores) - min(valores)) / valor
        if dispersion > DISPERSION_MAXIMA_ENTRE_PARES:
            logger.warning(
                "Los pares de CCL difieren %.1f%% entre sí (%s). Revisá los ratios en CCL_PARES.",
                dispersion * 100, ", ".join(f"{v:.2f}" for v in valores),
            )

    fuente = ("mediana de " if len(valores) > 1 else "") + " · ".join(pares_usados)
    _ccl_cache = (valor, now, fuente)
    logger.info("CCL calculado automáticamente vía %s: %.2f", fuente, valor)
    return {"valor": valor, "fuente": fuente}


def get_ccl_historico(period: str | None = None):
    """Serie histórica diaria de CCL, calculada con el primer par de
    settings.CCL_PARES que tenga histórico disponible. Necesaria para
    convertir precios de acciones argentinas directas a dólares equivalentes
    en toda la ventana histórica -- no solo hoy.

    Solo se usan los días en que cotizaron AMBAS puntas (BCBA y EEUU): rellenar
    hacia adelante una de las dos generaba un CCL "falso" en los feriados de
    un solo mercado (precio viejo de un lado contra precio nuevo del otro).
    """
    import pandas as pd

    period = period or settings.HISTORY_PERIOD
    for ticker_ars, ticker_usd, ratio in settings.CCL_PARES:
        hist_ars = data_providers.get_history(ticker_ars, period=period)
        hist_usd = data_providers.get_history(ticker_usd, period=period)
        if hist_ars is None or hist_usd is None or hist_ars.empty or hist_usd.empty:
            continue
        combinado = pd.concat([hist_ars, hist_usd], axis=1).dropna()
        if combinado.empty:
            continue
        ccl_serie = (combinado[ticker_ars] * ratio) / combinado[ticker_usd]
        ccl_serie.name = "CCL"
        logger.info("CCL histórico calculado vía %s/%s (%d días).", ticker_ars, ticker_usd, len(ccl_serie))
        return ccl_serie

    logger.warning("No se pudo calcular el CCL histórico con ningún par configurado.")
    return None


def ccl_en_fecha(ccl_historico, fecha) -> float | None:
    """Último CCL conocido a una fecha dada (o el más cercano posterior si la
    fecha es anterior al inicio de la serie). None si no hay serie."""
    import pandas as pd

    if ccl_historico is None or len(ccl_historico) == 0:
        return None
    ts = pd.Timestamp(fecha)
    anteriores = ccl_historico.loc[:ts]
    if not anteriores.empty:
        return float(anteriores.iloc[-1])
    return float(ccl_historico.iloc[0])
