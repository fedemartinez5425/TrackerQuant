"""Métricas de rendimiento sobre series sintéticas de resultado conocido (sin red)."""
import math

import numpy as np
import pandas as pd
import pytest

from core.performance import metrics as m


def _serie_crecimiento(tasa_anual: float, anios: float = 3.2, inicio: str = "2022-01-03") -> pd.Series:
    """Precio que crece a una tasa anual constante, en días hábiles."""
    fechas = pd.bdate_range(inicio, periods=int(anios * 252))
    t = (fechas - fechas[0]).days / m.DIAS_POR_ANIO
    return pd.Series(100 * (1 + tasa_anual) ** t, index=fechas)


def test_cagr_de_crecimiento_constante():
    serie = _serie_crecimiento(0.10)
    assert m.cagr(serie, 1) == pytest.approx(0.10, abs=1e-6)
    assert m.cagr(serie, 3) == pytest.approx(0.10, abs=1e-6)


def test_ventana_sin_historia_suficiente_devuelve_none():
    serie = _serie_crecimiento(0.10, anios=2)
    assert m.cagr(serie, 3) is None
    assert m.sharpe(serie, 3) is None
    assert m.cagr(serie, 1) is not None


def test_volatilidad_anual_es_std_diaria_por_raiz_252():
    rng = np.random.default_rng(0)
    fechas = pd.bdate_range("2022-01-03", periods=800)
    r = rng.normal(0, 0.01, len(fechas))
    serie = pd.Series(100 * np.cumprod(1 + r), index=fechas)
    esperado = serie.iloc[-253:].pct_change().dropna().std() * math.sqrt(252)
    # la ventana de 1 año calendario toma ~252 ruedas: mismo orden de magnitud exacto
    assert m.volatilidad_anual(serie, 1) == pytest.approx(esperado, rel=0.05)
    assert m.volatilidad_anual(serie, None) == pytest.approx(serie.pct_change().std() * math.sqrt(252))


def test_sharpe_y_sortino_usan_cagr_menos_rf():
    rng = np.random.default_rng(1)
    fechas = pd.bdate_range("2022-01-03", periods=800)
    serie = pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, len(fechas))), index=fechas)
    c, v = m.cagr(serie, 1), m.volatilidad_anual(serie, 1)
    assert m.sharpe(serie, 1, rf=0.04) == pytest.approx((c - 0.04) / v)
    r = m.ventana(serie, 1).pct_change().dropna()
    dd = r[r < 0].std() * math.sqrt(252)
    assert m.sortino(serie, 1, rf=0.04) == pytest.approx((c - 0.04) / dd)


def test_max_drawdown_y_drawdown_actual():
    fechas = pd.bdate_range("2024-01-01", periods=300)
    valores = np.concatenate([np.linspace(100, 200, 100), np.linspace(200, 120, 100), np.linspace(120, 150, 100)])
    serie = pd.Series(valores, index=fechas)
    assert m.max_drawdown(serie) == pytest.approx(120 / 200 - 1)
    assert m.drawdown_actual(serie) == pytest.approx(150 / 200 - 1)


def test_momentum_en_ruedas():
    serie = pd.Series(np.arange(1, 301, dtype=float), index=pd.bdate_range("2024-01-01", periods=300))
    assert m.retorno_ruedas(serie, 21) == pytest.approx(300 / 279 - 1)
    assert m.retorno_ruedas(serie, 126) == pytest.approx(300 / 174 - 1)
    assert m.momentum_12_1(serie) == pytest.approx(279 / 48 - 1)
    assert m.momentum_12_1(serie.iloc[:200]) is None


def test_vs_sma_y_rsi():
    serie = pd.Series(np.arange(1, 251, dtype=float), index=pd.bdate_range("2024-01-01", periods=250))
    assert m.vs_sma(serie, 50) == pytest.approx(250 / np.arange(201, 251).mean() - 1)
    assert m.vs_sma(serie.iloc[:100], 200) is None
    assert m.rsi(serie) == 100.0  # todas subas
    alterna = pd.Series([10, 12, 10, 12, 10, 12, 10, 12, 10, 12, 10, 12, 10, 12, 10, 12], dtype=float)
    assert m.rsi(alterna) == pytest.approx(50.0)  # subas y bajas iguales


def test_metricas_por_activo_arma_una_fila_por_ticker():
    precios = pd.concat([_serie_crecimiento(0.10).rename("A"), _serie_crecimiento(0.20).rename("B")], axis=1)
    df = m.metricas_por_activo(precios)
    assert list(df.index) == ["A", "B"]
    assert {"cagr_1a", "cagr_3a", "sharpe_3a", "max_dd_3a", "mom_12_1", "rsi_14", "vs_sma200"} <= set(df.columns)
    assert df.loc["B", "cagr_3a"] == pytest.approx(0.20, abs=1e-6)


def test_metricas_cartera_con_pesos_constantes():
    fechas = pd.bdate_range("2022-01-03", periods=820)
    a = pd.Series(100 * (1.001 ** np.arange(len(fechas))), index=fechas)
    precios = pd.DataFrame({"A": a, "B": a * 2})  # mismo retorno diario
    res = m.metricas_cartera(precios, {"A": 0.5, "B": 0.5})
    assert res["cagr_3a"] == pytest.approx(m.cagr(a, 3))
    assert res["max_dd_3a"] == pytest.approx(0.0)
    indice = m.indice_cartera(precios, {"A": 0.5, "B": 0.5})
    assert indice.iloc[0] == 1.0
    assert indice.iloc[-1] == pytest.approx(a.iloc[-1] / a.iloc[0])
