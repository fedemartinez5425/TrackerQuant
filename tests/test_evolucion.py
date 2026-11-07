"""Evolución real de la cartera: valor diario, aportes, rendimiento time-weighted y alertas."""
from datetime import date

import pandas as pd
import pytest

from config.settings import settings
from core.portfolio import evolucion as ev
from core.storage.models import REVERSO_PREFIJO, Currency, Instrumento, TipoInstrumento, Transaction, TransactionAction

LUNES = date(2026, 3, 2)
DIAS = pd.bdate_range(LUNES, periods=10)  # 2/3 al 13/3


def _tx(dia, ticker="GGAL", accion=TransactionAction.COMPRA, cantidad=10, precio=100.0, **kw):
    return Transaction(fecha=DIAS[dia].date(), ticker=ticker, accion=accion, cantidad=cantidad, precio=precio, **kw)


def _precios(**series):
    return pd.DataFrame({k: pd.Series(v, index=DIAS[: len(v)]) for k, v in series.items()})


def _ccl(valor=1000.0):
    return pd.Series(valor, index=DIAS)


def _evo(txs, precios, instrumentos=None, ccl=None):
    return ev.calcular_evolucion(txs, instrumentos or {}, precios, _ccl() if ccl is None else ccl, hasta=DIAS[-1].date())


def test_sin_operaciones_queda_vacia():
    assert _evo([], _precios()).vacia


def test_compra_y_suba_de_precio():
    e = _evo([_tx(0)], _precios(**{"GGAL.BA": [100, 110, 121] + [121] * 7}))
    d = e.diario
    assert d["valor_ars"].iloc[0] == pytest.approx(1000)
    assert d["valor_ars"].iloc[2] == pytest.approx(1210)
    assert d["aportes_ars"].iloc[-1] == pytest.approx(1000)
    assert e.indice("ARS").iloc[-1] == pytest.approx(121)
    r = e.resumen("ARS")
    assert r["ganancia"] == pytest.approx(210) and r["rendimiento"] == pytest.approx(0.21)
    assert d["valor_usd"].iloc[2] == pytest.approx(1.21)


def test_un_aporte_a_mitad_de_camino_no_cambia_el_rendimiento():
    precios = _precios(**{"GGAL.BA": [100, 110, 121] + [121] * 7})
    solo = _evo([_tx(0)], precios)
    con_aporte = _evo([_tx(0), _tx(1, cantidad=1000, precio=110)], precios)
    assert con_aporte.diario["valor_ars"].iloc[2] == pytest.approx(1010 * 121)
    assert con_aporte.indice("ARS").iloc[-1] == pytest.approx(solo.indice("ARS").iloc[-1])
    assert con_aporte.resumen("ARS")["aportes_netos"] == pytest.approx(1000 + 110_000)


def test_la_compra_cuenta_la_ganancia_del_mismo_dia():
    # Compró a 100 y cerró a 105: el rendimiento del día es +5 %, no 0.
    e = _evo([_tx(0)], _precios(**{"GGAL.BA": [105] * 10}))
    assert e.indice("ARS").iloc[0] == pytest.approx(105)


def test_la_venta_es_un_retiro_y_no_un_rendimiento():
    precios = _precios(**{"GGAL.BA": [100] * 10})
    e = _evo([_tx(0), _tx(3, accion=TransactionAction.VENTA, cantidad=4, comision=10)], precios)
    d = e.diario
    assert d["valor_ars"].iloc[3] == pytest.approx(600)
    assert d["flujo_ars"].iloc[3] == pytest.approx(-390)  # 400 − comisión
    assert d["aportes_ars"].iloc[-1] == pytest.approx(610)
    # La comisión es lo único que cuesta: −10 sobre 1000.
    assert e.indice("ARS").iloc[-1] == pytest.approx(99)
    assert e.resumen("ARS")["ganancia"] == pytest.approx(-10)


def test_vender_todo_deja_valor_cero_sin_romper():
    e = _evo([_tx(0), _tx(2, accion=TransactionAction.VENTA, cantidad=10)], _precios(**{"GGAL.BA": [100] * 10}))
    assert e.diario["valor_ars"].iloc[-1] == 0
    assert e.indice("ARS").notna().all()
    assert e.pesos.iloc[-1].sum() == 0


def test_reversos_excluidos():
    original = _tx(0, cantidad=50)
    reverso = _tx(1, accion=TransactionAction.VENTA, cantidad=50, notas=f"{REVERSO_PREFIJO}{original.id}")
    e = _evo([original, reverso, _tx(2)], _precios(**{"GGAL.BA": [100] * 10}))
    assert e.diario.index[0] == pd.Timestamp(DIAS[2])
    assert e.diario["aportes_ars"].iloc[-1] == pytest.approx(1000)


def test_operacion_en_usd_se_convierte_con_el_ccl_de_su_fecha():
    ccl = pd.Series([1000.0, 1000, 1200] + [1200] * 7, index=DIAS)
    e = _evo([_tx(2, precio=0.1, moneda=Currency.USD)], _precios(**{"GGAL.BA": [120] * 10}), ccl=ccl)
    assert e.diario["flujo_ars"].iloc[0] == pytest.approx(1200)
    assert e.diario["flujo_usd"].iloc[0] == pytest.approx(1)


def test_cedear_sin_ba_usa_el_teorico_del_adr():
    inst = {"AAPL": Instrumento(ticker="AAPL", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="AAPL", ratio_cedear=20)}
    e = _evo([_tx(0, ticker="AAPL", precio=10_000)], _precios(AAPL=[200] * 5 + [220] * 5), instrumentos=inst)
    assert e.diario["valor_ars"].iloc[0] == pytest.approx(10 * 200 / 20 * 1000)
    assert e.diario["valor_ars"].iloc[-1] == pytest.approx(10 * 220 / 20 * 1000)
    assert not e.alertas


def test_feriado_usa_el_ultimo_precio_y_fin_de_semana_cae_el_lunes():
    precios = pd.DataFrame({"GGAL.BA": [100.0, 102.0]}, index=[DIAS[0], DIAS[2]])  # el día 1 no cotizó
    sabado = Transaction(fecha=date(2026, 3, 7), ticker="GGAL", accion=TransactionAction.COMPRA, cantidad=1, precio=102)
    e = _evo([_tx(0), sabado], precios)
    assert e.diario["valor_ars"].iloc[1] == pytest.approx(1000)
    assert e.operaciones["fecha"].iloc[-1] == pd.Timestamp(date(2026, 3, 9))


def test_sin_precio_de_mercado_se_valua_a_la_operacion_y_avisa():
    e = _evo([_tx(0, ticker="RARA", precio=50)], _precios())
    assert e.diario["valor_ars"].iloc[-1] == pytest.approx(500)
    assert [a.tipo for a in e.alertas] == ["sin_precio"]


def test_alerta_si_el_precio_de_la_operacion_no_coincide_con_el_mercado():
    # Split 1:10 no cargado: operó a 1000 pero el precio ajustado de Yahoo es 100.
    e = _evo([_tx(0, precio=1000)], _precios(**{"GGAL.BA": [100] * 10}))
    assert any(a.tipo == "precio_operacion" and a.ticker == "GGAL" for a in e.alertas)


def test_alerta_por_salto_sin_operacion():
    e = _evo([_tx(0)], _precios(**{"GGAL.BA": [100] * 5 + [50] * 5}))
    saltos = [a for a in e.alertas if a.tipo == "salto"]
    assert len(saltos) == 1 and saltos[0].fecha == DIAS[5].date()


def test_resumen_de_un_periodo_parcial():
    precios = _precios(**{"GGAL.BA": [100, 100, 100, 100, 110, 110, 121, 121, 121, 121]})
    e = _evo([_tx(0), _tx(5, cantidad=10, precio=110)], precios)
    r = e.resumen("ARS", desde=DIAS[4].date())
    assert r["valor_inicial"] == pytest.approx(1100)
    assert r["aportes_netos"] == pytest.approx(1100)
    assert r["ganancia"] == pytest.approx(20 * 121 - 1100 - 1100)
    assert r["rendimiento"] == pytest.approx(0.10)
    assert e.indice("ARS", DIAS[4].date()).iloc[0] == 100


def test_pesos_y_composicion():
    precios = _precios(**{"GGAL.BA": [100] * 10, "YPFD.BA": [300] * 10})
    e = _evo([_tx(0), _tx(1, ticker="YPFD", precio=300)], precios)
    assert e.pesos.iloc[0].to_dict() == {"GGAL": 1.0, "YPFD": 0.0}
    assert e.pesos.iloc[-1]["YPFD"] == pytest.approx(0.75)


def test_referencias_en_pesos_incluyen_el_dolar():
    ccl = pd.Series([1000.0] * 5 + [1100.0] * 5, index=DIAS)
    precios = _precios(**{"GGAL.BA": [100] * 10, settings.DEFAULT_BENCHMARK: [500] * 10})
    e = _evo([_tx(0)], precios, ccl=ccl)
    ref = ev.referencias(e, precios, "ARS")
    assert ref["Dólar CCL"].iloc[-1] == pytest.approx(110)
    assert ref[settings.DEFAULT_BENCHMARK].iloc[-1] == pytest.approx(110)
    assert list(ev.referencias(e, precios, "USD").columns) == [settings.DEFAULT_BENCHMARK]


def test_tickers_necesarios_y_periodo():
    inst = {"AAPL": Instrumento(ticker="AAPL", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="AAPL", ratio_cedear=20)}
    assert ev.tickers_necesarios([_tx(0, ticker="AAPL"), _tx(0)], inst) == ["AAPL.BA", "AAPL", "GGAL.BA"]
    assert ev.periodo_desde(date(2026, 1, 1), date(2026, 11, 1)) == "1y"
    assert ev.periodo_desde(date(2022, 1, 1), date(2026, 11, 1)) == "5y"

