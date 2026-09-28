"""
Valida los forecasts que ya se guardaron (core/storage/models.py ->
PortfolioForecast) contra lo que realmente pasó. La volatilidad realizada
NUNCA se persiste -- siempre se recalcula on-the-fly a partir del
histórico de precios + los pesos que estaban vigentes en el momento del
forecast (guardados en composicion_json). Esto mantiene el storage
append-only y siempre exacto (no puede desincronizarse un valor cacheado
de la realidad).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from core.forecasting.volatility_garch import calcular_vol_realizada_ventana
from core.portfolio.historicos import InstrumentoRiesgo, historicos_usd_equivalente
from core.risk.volatility import retorno_diario_cartera
from core.storage.models import PortfolioForecast


def forecast_ya_resuelto(forecast: PortfolioForecast) -> bool:
    fecha_resolucion = forecast.fecha + timedelta(days=int(forecast.horizonte_dias * 1.45))  # ~hábiles a corridos
    return fecha_resolucion <= date.today()


def evaluar_forecast(
    forecast: PortfolioForecast, instrumentos_por_ticker: dict
) -> dict | None:
    """Recalcula la volatilidad realizada en la ventana que sucedió a un
    forecast pasado, usando los MISMOS pesos que tenía la cartera en ese
    momento (guardados junto al forecast). Devuelve None si el horizonte
    todavía no transcurrió o si faltan datos."""
    if not forecast_ya_resuelto(forecast):
        return None

    try:
        pesos = json.loads(forecast.composicion_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not pesos:
        return None

    instrumentos = [
        InstrumentoRiesgo(ticker, instrumentos_por_ticker[ticker].tipo_instrumento, instrumentos_por_ticker[ticker].ticker_usd)
        for ticker in pesos
        if ticker in instrumentos_por_ticker
    ]
    if not instrumentos:
        return None

    historicos = historicos_usd_equivalente(instrumentos, period="2y")
    if historicos.empty:
        return None

    retornos = historicos.pct_change().dropna(how="all")
    retorno_cartera = retorno_diario_cartera(retornos, pesos)
    vol_realizada = calcular_vol_realizada_ventana(retorno_cartera, forecast.fecha, forecast.horizonte_dias)
    if vol_realizada is None:
        return None

    error_pp = (vol_realizada - forecast.vol_pronosticada_anual) * 100  # en puntos porcentuales
    return {
        "fecha_forecast": forecast.fecha,
        "horizonte_dias": forecast.horizonte_dias,
        "vol_pronosticada": forecast.vol_pronosticada_anual,
        "vol_realizada": vol_realizada,
        "error_pp": error_pp,
    }


def tabla_backtest(forecasts: list[PortfolioForecast], instrumentos_por_ticker: dict) -> pd.DataFrame:
    filas = [evaluar_forecast(f, instrumentos_por_ticker) for f in forecasts]
    filas = [f for f in filas if f is not None]
    if not filas:
        return pd.DataFrame(
            columns=["fecha_forecast", "horizonte_dias", "vol_pronosticada", "vol_realizada", "error_pp"]
        )
    return pd.DataFrame(filas).sort_values("fecha_forecast", ascending=False)
