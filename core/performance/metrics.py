"""
Métricas de rendimiento para activos y para la cartera.

Entrada: precios diarios en USD equivalente, una columna por ticker BCBA
(salida de `historicos_usd_equivalente` + `alinear_dias_comunes`), con
DatetimeIndex. Las definiciones exactas están en CLAUDE.md ("Definiciones
de métricas") -- si cambiás una fórmula acá, actualizala allá.

Ventanas: las métricas de rendimiento/riesgo se miden sobre los últimos
`ventana_anios` años CALENDARIO (no N filas: con días comunes entre BCBA y
NYSE hay menos de 252 ruedas por año). Si la historia no cubre la ventana
(con un margen de `COBERTURA_MINIMA`), la métrica queda en None: mejor
"sin dato" que un CAGR a 3 años calculado con 8 meses.

Momentum y técnicos sí se miden en ruedas (21/63/126/252, SMA50/200, RSI 14).
"""
from __future__ import annotations

import math

import pandas as pd

from config.settings import settings
from core.risk.volatility import TRADING_DAYS_PER_YEAR, retorno_diario_cartera

VENTANAS_ANIOS = (1, 3)
COBERTURA_MINIMA = 0.95  # la serie tiene que cubrir al menos el 95% de la ventana
DIAS_POR_ANIO = 365.25

RUEDAS_1M, RUEDAS_3M, RUEDAS_6M, RUEDAS_12M = 21, 63, 126, 252


def _limpia(precios: pd.Series) -> pd.Series:
    return precios.dropna().astype(float)


def _anios(serie: pd.Series) -> float:
    if isinstance(serie.index, pd.DatetimeIndex):
        return (serie.index[-1] - serie.index[0]).days / DIAS_POR_ANIO
    return (len(serie) - 1) / TRADING_DAYS_PER_YEAR


def ventana(precios: pd.Series, ventana_anios: float | None) -> pd.Series | None:
    """Últimos `ventana_anios` años de la serie, o None si no hay historia
    suficiente. ventana_anios=None devuelve toda la serie."""
    serie = _limpia(precios)
    if len(serie) < 2:
        return None
    if ventana_anios is None:
        return serie
    if isinstance(serie.index, pd.DatetimeIndex):
        inicio = serie.index[-1] - pd.DateOffset(days=round(ventana_anios * DIAS_POR_ANIO))
        recorte = serie.loc[serie.index >= inicio]
    else:
        recorte = serie.iloc[-(int(ventana_anios * TRADING_DAYS_PER_YEAR) + 1):]
    if len(recorte) < 2 or _anios(recorte) < ventana_anios * COBERTURA_MINIMA:
        return None
    return recorte


def _retornos(serie: pd.Series) -> pd.Series:
    return serie.pct_change().dropna()


# ---------------- Rendimiento y riesgo (por ventana) ----------------
def cagr(precios: pd.Series, ventana_anios: float | None = None) -> float | None:
    """(precio final / precio inicial) ^ (1 / años) − 1."""
    serie = ventana(precios, ventana_anios)
    if serie is None or serie.iloc[0] <= 0:
        return None
    anios = _anios(serie)
    if anios <= 0:
        return None
    return float((serie.iloc[-1] / serie.iloc[0]) ** (1 / anios) - 1)


def volatilidad_anual(precios: pd.Series, ventana_anios: float | None = None) -> float | None:
    """Desvío estándar de los retornos diarios × √252."""
    serie = ventana(precios, ventana_anios)
    if serie is None:
        return None
    r = _retornos(serie)
    if len(r) < 2:
        return None
    return float(r.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe(precios: pd.Series, ventana_anios: float | None = None, rf: float | None = None) -> float | None:
    """(CAGR − rf) / volatilidad anual."""
    rf = settings.RISK_FREE_RATE if rf is None else rf
    c, v = cagr(precios, ventana_anios), volatilidad_anual(precios, ventana_anios)
    if c is None or not v:
        return None
    return (c - rf) / v


def sortino(precios: pd.Series, ventana_anios: float | None = None, rf: float | None = None) -> float | None:
    """(CAGR − rf) / (desvío de los retornos diarios NEGATIVOS × √252)."""
    rf = settings.RISK_FREE_RATE if rf is None else rf
    serie = ventana(precios, ventana_anios)
    c = cagr(precios, ventana_anios)
    if serie is None or c is None:
        return None
    negativos = _retornos(serie)
    negativos = negativos[negativos < 0]
    if len(negativos) < 2 or negativos.std() == 0:
        return None
    return (c - rf) / float(negativos.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(precios: pd.Series, ventana_anios: float | None = None) -> float | None:
    """Peor caída desde un máximo previo dentro de la ventana:
    mínimo de (precio / máximo acumulado − 1). Negativo o 0."""
    serie = ventana(precios, ventana_anios)
    if serie is None:
        return None
    return float((serie / serie.cummax() - 1).min())


# ---------------- Momentum y técnicos (en ruedas) ----------------
def drawdown_actual(precios: pd.Series) -> float | None:
    """Precio de hoy / máximo de las últimas 252 ruedas − 1."""
    serie = _limpia(precios)
    if serie.empty:
        return None
    return float(serie.iloc[-1] / serie.iloc[-RUEDAS_12M:].max() - 1)


def retorno_ruedas(precios: pd.Series, ruedas: int) -> float | None:
    """Precio de hoy / precio de hace `ruedas` ruedas − 1."""
    serie = _limpia(precios)
    if len(serie) <= ruedas:
        return None
    return float(serie.iloc[-1] / serie.iloc[-1 - ruedas] - 1)


def momentum_12_1(precios: pd.Series) -> float | None:
    """Precio de hace 21 ruedas / precio de hace 252 ruedas − 1 (saltea el
    último mes, que suele revertir)."""
    serie = _limpia(precios)
    if len(serie) <= RUEDAS_12M:
        return None
    return float(serie.iloc[-1 - RUEDAS_1M] / serie.iloc[-1 - RUEDAS_12M] - 1)


def vs_sma(precios: pd.Series, ruedas: int) -> float | None:
    """Precio de hoy / promedio simple de las últimas `ruedas` ruedas − 1."""
    serie = _limpia(precios)
    if len(serie) < ruedas:
        return None
    return float(serie.iloc[-1] / serie.iloc[-ruedas:].mean() - 1)


def rsi(precios: pd.Series, ruedas: int = 14) -> float | None:
    """RSI simple: RS = promedio de subas / promedio de bajas (en valor
    absoluto) de los últimos `ruedas` cambios; RSI = 100 − 100 / (1 + RS).
    Sin bajas: 100 (y 50 si tampoco hubo subas)."""
    serie = _limpia(precios)
    if len(serie) <= ruedas:
        return None
    cambios = serie.diff().iloc[-ruedas:]
    subas = cambios.clip(lower=0).mean()
    bajas = (-cambios.clip(upper=0)).mean()
    if bajas == 0:
        return 100.0 if subas > 0 else 50.0
    return float(100 - 100 / (1 + subas / bajas))


# ---------------- Agregados ----------------
def metricas_serie(
    precios: pd.Series, ventanas: tuple = VENTANAS_ANIOS, rf: float | None = None
) -> dict[str, float | None]:
    """Todas las métricas de una serie de precios (o de un índice de cartera)."""
    fila: dict[str, float | None] = {}
    for n in ventanas:
        fila[f"cagr_{n}a"] = cagr(precios, n)
        fila[f"vol_{n}a"] = volatilidad_anual(precios, n)
        fila[f"sharpe_{n}a"] = sharpe(precios, n, rf)
        fila[f"sortino_{n}a"] = sortino(precios, n, rf)
        fila[f"max_dd_{n}a"] = max_drawdown(precios, n)
    fila["drawdown_actual"] = drawdown_actual(precios)
    fila["ret_1m"] = retorno_ruedas(precios, RUEDAS_1M)
    fila["ret_3m"] = retorno_ruedas(precios, RUEDAS_3M)
    fila["ret_6m"] = retorno_ruedas(precios, RUEDAS_6M)
    fila["mom_12_1"] = momentum_12_1(precios)
    fila["vs_sma50"] = vs_sma(precios, 50)
    fila["vs_sma200"] = vs_sma(precios, 200)
    fila["rsi_14"] = rsi(precios, 14)
    return fila


def metricas_por_activo(
    precios: pd.DataFrame, ventanas: tuple = VENTANAS_ANIOS, rf: float | None = None
) -> pd.DataFrame:
    """Una fila por ticker (columna de `precios`), una columna por métrica.
    Las métricas sin historia suficiente quedan en NaN."""
    if precios is None or precios.empty:
        return pd.DataFrame()
    filas = {ticker: metricas_serie(precios[ticker], ventanas, rf) for ticker in precios.columns}
    return pd.DataFrame.from_dict(filas, orient="index").astype(float)


def indice_cartera(precios: pd.DataFrame, pesos: dict[str, float]) -> pd.Series:
    """Valor de $1 invertido con pesos CONSTANTES (rebalanceo diario), arrancando
    en 1 el primer día. Reusa `retorno_diario_cartera` (re-normaliza pesos
    de activos sin datos)."""
    if precios is None or precios.empty:
        return pd.Series(dtype=float)
    retornos = precios.pct_change().iloc[1:]
    r = retorno_diario_cartera(retornos, pesos)
    if r.empty:
        return pd.Series(dtype=float)
    indice = (1 + r).cumprod()
    inicio = pd.Series([1.0], index=[precios.index[0]])
    return pd.concat([inicio, indice]).rename("CARTERA")


def metricas_cartera(
    precios: pd.DataFrame, pesos: dict[str, float], ventanas: tuple = VENTANAS_ANIOS, rf: float | None = None
) -> dict[str, float | None]:
    """Las mismas métricas de `metricas_serie`, para la cartera con pesos constantes."""
    indice = indice_cartera(precios, pesos)
    if indice.empty:
        return {k: None for k in metricas_serie(pd.Series(dtype=float), ventanas, rf)}
    return metricas_serie(indice, ventanas, rf)
