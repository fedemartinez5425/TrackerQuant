"""Semáforos de tablas: umbrales, faltantes y Styler (sin Streamlit)."""
import math

import pandas as pd

from core.risk.volatility import semaforo_riesgo
from core.viz import semaforos as s


def test_umbrales_por_regla():
    assert s.nivel(0.05, "signo") == s.VERDE
    assert s.nivel(-0.01, "signo") == s.ROJO
    assert s.nivel(0, "signo") is None
    assert s.nivel(-0.01, "signo_inverso") == s.VERDE

    assert [s.nivel(v, "volatilidad") for v in (0.20, 0.30, 0.45)] == [s.VERDE, s.AMARILLO, s.ROJO]
    assert [s.nivel(v, "peso") for v in (0.10, 0.20, 0.30)] == [s.VERDE, s.AMARILLO, s.ROJO]
    assert [s.nivel(v, "correlacion") for v in (0.2, 0.5, 0.8)] == [s.VERDE, s.AMARILLO, s.ROJO]
    assert [s.nivel(v, "drawdown") for v in (-0.10, -0.25, -0.40)] == [s.VERDE, s.AMARILLO, s.ROJO]
    assert [s.nivel(v, "prima") for v in (-0.02, 0.04, -0.08)] == [s.VERDE, s.AMARILLO, s.ROJO]
    assert [s.nivel(v, "rsi") for v in (25, 50, 75)] == [s.ROJO, s.VERDE, s.ROJO]
    assert [s.nivel(v, "error_pp") for v in (1, -3, 6)] == [s.VERDE, s.AMARILLO, s.ROJO]


def test_faltantes_no_rompen():
    for v in (None, math.nan, float("nan"), "—", "abc", True):
        assert s.nivel(v, "signo") is None
    assert s.css(None) == ""


def test_umbrales_de_vol_coinciden_con_el_semaforo_del_dashboard():
    # Misma vol, concentración baja: el Dashboard y la tabla tienen que coincidir.
    assert "BAJO" in semaforo_riesgo(s.VOL_MEDIA - 0.01, 0.1)
    assert "MEDIO" in semaforo_riesgo(s.VOL_MEDIA + 0.01, 0.1)
    assert "ALTO" in semaforo_riesgo(s.VOL_ALTA + 0.01, 0.1)


def test_senal_toma_el_peor_nivel():
    assert s.senal([s.VERDE, None, s.AMARILLO]) == "🟡"
    assert s.senal([s.VERDE, s.ROJO]) == "🔴"
    assert s.senal([None]) == ""

    df = pd.DataFrame({"gp": [0.1, -0.2, None], "peso": [0.1, 0.1, 0.3]})
    assert list(s.columna_senal(df, {"gp": "signo", "peso": "peso", "no_existe": "signo"})) == ["🟢", "🔴", "🔴"]


def test_estilar_pinta_celdas_y_tolera_nan():
    df = pd.DataFrame({"G/P %": [0.1, -0.1, None], "Texto": ["a", "b", "c"]}, index=["A", "B", "C"])
    html = s.estilar(df.style.format({"G/P %": "{:.1%}"}, na_rep="—"), {"G/P %": "signo", "Falta": "signo"}).to_html()
    assert s.css(s.VERDE).split(";")[0] in html
    assert "background-color: rgba(255, 92, 108, 0.12)" in html

    filas = pd.DataFrame({"Actual": [0.3, 0.5], "Escenario": [0.2, None]}, index=["Vol", "Corr"])
    html = s.estilar_filas(filas, {"Vol": "volatilidad", "Corr": "correlacion", "No": "signo"}).to_html()
    assert s.css(s.AMARILLO).split(";")[0] in html
