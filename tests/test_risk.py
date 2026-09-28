import numpy as np
import pandas as pd

from core.risk.correlation import correlacion_promedio_simple, matriz_correlacion
from core.risk.var import cvar_historico, peor_dia_historico, var_historico
from core.risk.volatility import retorno_diario_cartera, semaforo_riesgo, volatilidad_anualizada
from core.risk.stress_test import beta_ponderado_cartera, betas_por_activo


def _retornos_sinteticos(n=300, seed=42):
    rng = np.random.default_rng(seed)
    fechas = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "AAA": rng.normal(0.0005, 0.02, n),
            "BBB": rng.normal(0.0003, 0.015, n),
            "SPY": rng.normal(0.0004, 0.01, n),
        },
        index=fechas,
    )


def test_retorno_diario_cartera_pondera_correctamente():
    retornos = _retornos_sinteticos()
    pesos = {"AAA": 0.6, "BBB": 0.4}
    r_cartera = retorno_diario_cartera(retornos, pesos)
    esperado = retornos["AAA"] * 0.6 + retornos["BBB"] * 0.4
    pd.testing.assert_series_equal(r_cartera, esperado, check_names=False)


def test_volatilidad_anualizada_es_positiva():
    retornos = _retornos_sinteticos()
    r_cartera = retorno_diario_cartera(retornos, {"AAA": 0.5, "BBB": 0.5})
    vol = volatilidad_anualizada(r_cartera)
    assert vol is not None and vol > 0


def test_var_historico_es_mas_conservador_que_cero():
    retornos = _retornos_sinteticos()
    r_cartera = retorno_diario_cartera(retornos, {"AAA": 0.5, "BBB": 0.5})
    var95 = var_historico(r_cartera, 0.95)
    assert var95 is not None and var95 < 0  # una pérdida, por definición negativa


def test_cvar_es_mas_extremo_que_var():
    retornos = _retornos_sinteticos()
    r_cartera = retorno_diario_cartera(retornos, {"AAA": 0.5, "BBB": 0.5})
    var95 = var_historico(r_cartera, 0.95)
    cvar95 = cvar_historico(r_cartera, 0.95)
    # el CVaR promedia la cola más allá del VaR -> debe ser igual o peor (más negativo)
    assert cvar95 <= var95


def test_peor_dia_historico_coincide_con_el_minimo():
    retornos = _retornos_sinteticos()
    r_cartera = retorno_diario_cartera(retornos, {"AAA": 0.5, "BBB": 0.5})
    peor_pct, peor_fecha = peor_dia_historico(r_cartera)
    assert peor_pct == r_cartera.min()
    assert peor_fecha == r_cartera.idxmin()


def test_correlacion_promedio_entre_menos1_y_1():
    retornos = _retornos_sinteticos()
    matriz = matriz_correlacion(retornos[["AAA", "BBB"]])
    promedio = correlacion_promedio_simple(matriz)
    assert -1 <= promedio <= 1


def test_semaforo_riesgo_alto_con_alta_volatilidad():
    assert semaforo_riesgo(0.5, 0.3) == "🔴 RIESGO ALTO"


def test_semaforo_riesgo_bajo_con_baja_volatilidad_y_concentracion():
    assert semaforo_riesgo(0.10, 0.30) == "🟢 RIESGO BAJO"


def test_beta_ponderado_cartera():
    retornos = _retornos_sinteticos()
    betas = betas_por_activo(retornos, "SPY")
    assert "AAA" in betas and "BBB" in betas
    beta_cartera = beta_ponderado_cartera(betas, {"AAA": 0.5, "BBB": 0.5})
    assert beta_cartera is not None
