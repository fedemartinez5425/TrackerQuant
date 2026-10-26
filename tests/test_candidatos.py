"""Evaluación de candidatos con series sintéticas y precios mockeados (sin red)."""
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from core.decision import candidatos as c
from core.storage.models import Instrumento, TipoInstrumento


def _precios(n=820, seed=0):
    """A y B muy correlacionadas entre sí; C independiente y menos volátil; D = copia de A."""
    rng = np.random.default_rng(seed)
    fechas = pd.bdate_range("2022-01-03", periods=n)
    factor = rng.normal(0.0004, 0.015, n)
    a = factor + rng.normal(0, 0.003, n)
    b = factor + rng.normal(0, 0.003, n)
    cc = rng.normal(0.0004, 0.006, n)
    df = pd.DataFrame({"A": a, "B": b, "C": cc}, index=fechas)
    precios = 100 * (1 + df).cumprod()
    precios["D"] = precios["A"] * 3
    return precios


def test_pesos_con_candidato_escala_la_cartera():
    nuevos = c.pesos_con_candidato({"A": 0.6, "B": 0.4}, "C", 0.10)
    assert nuevos == pytest.approx({"A": 0.54, "B": 0.36, "C": 0.10})
    assert sum(nuevos.values()) == pytest.approx(1.0)
    # si ya está en cartera, se suma encima
    assert c.pesos_con_candidato({"A": 0.5, "B": 0.5}, "A", 0.2) == pytest.approx({"A": 0.6, "B": 0.4})


def test_candidato_descorrelacionado_baja_la_vol_y_se_reporta_la_mas_correlacionada():
    precios = _precios()
    ev = c.evaluar_candidato(precios, {"A": 0.5, "B": 0.5}, "C", 0.2)
    assert ev["delta_vol_1a"] < 0
    assert ev["delta_vol_3a"] < 0
    assert abs(ev["corr_cartera"]) < 0.2

    ev_d = c.evaluar_candidato(precios, {"A": 0.5, "B": 0.5}, "D", 0.2)
    assert ev_d["mas_correlacionada"] == "A"
    assert ev_d["corr_mas_correlacionada"] == pytest.approx(1.0)
    assert set(ev_d["corr_posiciones"].index) == {"A", "B"}


def test_candidato_sin_historicos_devuelve_error():
    ev = c.evaluar_candidato(_precios(), {"A": 1.0}, "ZZZ")
    assert "error" in ev


def test_candidato_con_historia_corta_no_achica_a_los_demas_y_queda_sin_3a():
    precios = _precios()
    precios.loc[precios.index[:500], "C"] = np.nan  # C empezó a cotizar hace ~1,2 años
    ev = c.evaluar_candidato(precios, {"A": 0.5, "B": 0.5}, "C")
    assert ev["delta_vol_1a"] is not None
    assert ev["delta_sharpe_3a"] is None


def test_rankear_ordena_por_delta_sharpe_3a():
    precios = _precios()
    df = c.rankear_candidatos(precios, {"A": 0.5, "B": 0.5}, ["D", "C", "ZZZ"], 0.2)
    assert list(df.index)[-1] == "ZZZ"  # sin dato al final
    validos = df["delta_sharpe_3a"].dropna()
    assert list(validos) == sorted(validos, reverse=True)
    assert {"delta_vol_1a", "delta_max_dd_3a", "corr_cartera", "mas_correlacionada"} <= set(df.columns)


def test_precio_unidad_cedear_usa_adr_por_ccl_sobre_ratio():
    meta = Instrumento(ticker="META", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="META", ratio_cedear=24)
    with patch("core.decision.candidatos.data_providers.get_price", return_value=700.0):
        assert c.precio_unidad_ars(meta, ccl=1500.0) == pytest.approx(700 * 1500 / 24)


def test_precio_unidad_cedear_sin_ratio_lo_busca_en_comafi():
    meta = Instrumento(ticker="META", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="META", ratio_cedear=24)
    meta.ratio_cedear = None  # como un item de watchlist cargado sin ratio
    with patch("core.decision.candidatos.data_providers.get_price", return_value=700.0), patch(
        "core.data_providers.comafi_ratios.obtener_ratio", return_value=24.0
    ):
        assert c.precio_unidad_ars(meta, ccl=1500.0) == pytest.approx(43_750.0)


def test_precio_unidad_accion_arg_es_el_precio_bcba():
    vist = Instrumento(ticker="PAMP", tipo_instrumento=TipoInstrumento.ACCION_ARG)
    with patch("core.decision.candidatos.data_providers.get_price", side_effect=lambda t: {"PAMP.BA": 4000.0}.get(t)):
        assert c.precio_unidad_ars(vist) == 4000.0


def test_peso_de_una_unidad_y_unidades_enteras():
    assert c.peso_de_una_unidad(46_500, 106_000) == pytest.approx(0.4387, abs=1e-4)
    assert c.peso_de_una_unidad(None, 106_000) is None
    # 10% de la cartera resultante: monto = 106.000 × 0,1 / 0,9 ≈ 11.778 -> 2 unidades de $5.000
    assert c.unidades_para_peso(5_000, 106_000, 0.10) == 2
    assert c.unidades_para_peso(46_500, 106_000, 0.10) == 0
