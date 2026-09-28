from datetime import date, timedelta

import numpy as np
import pandas as pd

from core.forecasting.backtest import forecast_ya_resuelto
from core.forecasting.returns_forecast import cono_incertidumbre, proyectar_retorno_acumulado
from core.forecasting.volatility_garch import (
    calcular_vol_realizada_ventana,
    clasificar_regimen,
    resumen_forecast_volatilidad,
)
from core.storage.models import PortfolioForecast


def _retornos_sinteticos(n=750, seed=7):
    rng = np.random.default_rng(seed)
    fechas = pd.bdate_range("2022-01-01", periods=n)
    return pd.Series(rng.normal(0.0004, 0.015, n), index=fechas)


def test_resumen_forecast_volatilidad_devuelve_none_con_pocos_datos():
    retornos_cortos = _retornos_sinteticos(n=50)
    assert resumen_forecast_volatilidad(retornos_cortos, horizonte_dias=10) is None


def test_resumen_forecast_volatilidad_estructura_completa():
    retornos = _retornos_sinteticos()
    resumen = resumen_forecast_volatilidad(retornos, horizonte_dias=10)
    assert resumen is not None
    assert len(resumen["forecast_path"]) == 10
    assert resumen["vol_actual"] > 0
    assert resumen["vol_n_dias"] > 0
    assert "regimen" in resumen


def test_clasificar_regimen_alto_bajo_normal():
    assert "alta" in clasificar_regimen(0.50, 0.30).lower()
    assert "baja" in clasificar_regimen(0.10, 0.30).lower()
    assert "normal" in clasificar_regimen(0.30, 0.30).lower()


def test_proyectar_retorno_acumulado_banda_simetrica_alrededor_del_esperado():
    retornos = _retornos_sinteticos()
    proyeccion = proyectar_retorno_acumulado(retornos, horizonte_dias=10, vol_anual_forecast=0.25)
    centro_68 = (proyeccion["banda_68_inf"] + proyeccion["banda_68_sup"]) / 2
    assert abs(centro_68 - proyeccion["retorno_esperado_pct"]) < 1e-9
    # la banda 95% debe ser mas ancha que la 68%
    ancho_68 = proyeccion["banda_68_sup"] - proyeccion["banda_68_inf"]
    ancho_95 = proyeccion["banda_95_sup"] - proyeccion["banda_95_inf"]
    assert ancho_95 > ancho_68


def test_cono_incertidumbre_se_ensancha_con_el_horizonte():
    retornos = _retornos_sinteticos()
    forecast_path = pd.Series([0.20] * 10, index=range(1, 11))
    cono = cono_incertidumbre(retornos, forecast_path, valor_actual=100000)
    ancho_dia1 = cono.loc[1, "banda_95_sup"] - cono.loc[1, "banda_95_inf"]
    ancho_dia10 = cono.loc[10, "banda_95_sup"] - cono.loc[10, "banda_95_inf"]
    assert ancho_dia10 > ancho_dia1


def test_calcular_vol_realizada_ventana_none_si_faltan_datos():
    retornos = _retornos_sinteticos()
    fecha_futura_lejana = retornos.index[-1] + timedelta(days=365)
    assert calcular_vol_realizada_ventana(retornos, fecha_futura_lejana, 10) is None


def test_forecast_ya_resuelto_por_fecha():
    viejo = PortfolioForecast(
        fecha=date.today() - timedelta(days=60), horizonte_dias=10, vol_pronosticada_anual=0.25,
        composicion_json="{}",
    )
    reciente = PortfolioForecast(
        fecha=date.today(), horizonte_dias=10, vol_pronosticada_anual=0.25, composicion_json="{}",
    )
    assert forecast_ya_resuelto(viejo) is True
    assert forecast_ya_resuelto(reciente) is False
