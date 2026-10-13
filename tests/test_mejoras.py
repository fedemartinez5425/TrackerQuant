"""Tests de los arreglos de correctitud: reversos, moneda, calendarios,
CCL por mediana, forecast del horizonte, importación y caches."""
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from core.storage.csv_repository import CsvRepository
from core.storage.models import (
    Currency,
    Instrumento,
    TipoInstrumento,
    Transaction,
    TransactionAction,
    transacciones_efectivas,
)


def _repo(tmp_path):
    return CsvRepository(
        transactions_file=tmp_path / "transactions.csv",
        audit_file=tmp_path / "audit_log.csv",
        snapshots_file=tmp_path / "portfolio_snapshots.csv",
        instrumentos_file=tmp_path / "instrumentos.csv",
        processed_files_file=tmp_path / "processed_files.csv",
        forecasts_file=tmp_path / "forecast_log.csv",
    )


def _t(ticker, accion, cantidad, precio, fecha="2024-01-01", moneda="ARS"):
    return Transaction(
        fecha=date.fromisoformat(fecha), ticker=ticker, accion=TransactionAction(accion),
        cantidad=cantidad, precio=precio, moneda=Currency(moneda),
    )


# ---------------- Reversos ----------------
def test_reverso_anula_la_transaccion_y_no_altera_el_costo(tmp_path):
    from core.portfolio.portfolio_engine import calcular_tenencias

    repo = _repo(tmp_path)
    compra_buena = _t("AAPL", "COMPRA", 10, 100, "2024-01-01")
    compra_erronea = _t("AAPL", "COMPRA", 10, 300, "2024-02-01")
    repo.add_transactions([compra_buena, compra_erronea])
    repo.add_reversal(compra_erronea.id, "cargada por error", usuario="fede")

    tenencias = calcular_tenencias(repo.list_transactions())
    assert tenencias["AAPL"]["cantidad"] == 10
    assert tenencias["AAPL"]["costo_total"] == 1000  # sin rastro de la compra anulada


def test_no_se_puede_reversar_dos_veces_ni_reversar_un_reverso(tmp_path):
    repo = _repo(tmp_path)
    t = _t("AAPL", "COMPRA", 10, 100)
    repo.add_transaction(t)
    reverso = repo.add_reversal(t.id, "error", usuario="fede")
    with pytest.raises(ValueError, match="ya fue reversada"):
        repo.add_reversal(t.id, "otra vez", usuario="fede")
    with pytest.raises(ValueError, match="ya es un reverso"):
        repo.add_reversal(reverso.id, "reverso del reverso", usuario="fede")


def test_reverso_posterior_anula_tambien_en_la_reconstruccion_historica(tmp_path):
    from core.portfolio.portfolio_engine import calcular_tenencias_a_fecha

    repo = _repo(tmp_path)
    t = _t("AAPL", "COMPRA", 10, 100, "2024-01-01")
    repo.add_transaction(t)
    repo.add_reversal(t.id, "nunca existió", usuario="fede")  # reverso fechado HOY
    assert calcular_tenencias_a_fecha(repo.list_transactions(), date(2024, 6, 1)) == {}


def test_transacciones_efectivas_respeta_formato_historico_de_notas():
    original = _t("AAPL", "COMPRA", 1, 100)
    reverso = _t("AAPL", "VENTA", 1, 100)
    reverso.notas = f"REVERSO de {original.id} — motivo: test"
    assert transacciones_efectivas([original, reverso]) == []


# ---------------- Moneda ----------------
def test_transaccion_en_usd_se_convierte_a_pesos_al_ccl_de_su_fecha():
    from core.portfolio.portfolio_engine import calcular_tenencias

    txs = [_t("AAPL", "COMPRA", 10, 100, "2024-01-01", "ARS"), _t("AAPL", "COMPRA", 10, 1, "2024-03-01", "USD")]
    fx = {date(2024, 3, 1): 1000.0}
    tenencias = calcular_tenencias(txs, fx_usd_ars=lambda f: fx.get(f))
    assert tenencias["AAPL"]["costo_total"] == 10 * 100 + 10 * 1 * 1000


def test_normalizar_moneda_del_broker():
    from core.importers.broker_movimientos import normalizar_moneda

    for texto in ("Pesos", "$", "ARS", "", None):
        assert normalizar_moneda(texto) == "ARS"
    for texto in ("USD", "US$", "Dólares", "U$S", "Dolar MEP"):
        assert normalizar_moneda(texto) == "USD"


# ---------------- Calendarios ----------------
def test_alinear_dias_comunes_descarta_feriados_de_un_solo_mercado():
    from core.portfolio.historicos import alinear_dias_comunes

    fechas = pd.bdate_range("2024-01-01", periods=200)
    df = pd.DataFrame({"AAA": np.linspace(10, 20, 200), "SPY": np.linspace(100, 120, 200)}, index=fechas)
    df.iloc[50, 0] = np.nan  # feriado en BCBA, EEUU abierto
    alineado = alinear_dias_comunes(df)
    assert fechas[50] not in alineado.index
    assert len(alineado) == 199
    # No hay retornos de 0% inventados
    assert (alineado.pct_change().dropna() != 0).all().all()


def test_alinear_dias_comunes_excluye_activo_con_historia_corta():
    from core.portfolio.historicos import alinear_dias_comunes

    fechas = pd.bdate_range("2023-01-01", periods=400)
    df = pd.DataFrame({"VIEJO": np.linspace(10, 20, 400), "SPY": np.linspace(100, 120, 400)}, index=fechas)
    df["NUEVO"] = np.nan
    df.iloc[-30:, df.columns.get_loc("NUEVO")] = np.linspace(5, 6, 30)  # solo 30 días de historia
    alineado = alinear_dias_comunes(df, min_dias=120)
    assert "NUEVO" not in alineado.columns
    assert alineado.attrs["excluidos"] == ["NUEVO"]
    assert len(alineado) == 400


def test_retorno_cartera_redistribuye_peso_de_activo_sin_datos():
    from core.risk.volatility import retorno_diario_cartera

    fechas = pd.bdate_range("2024-01-01", periods=5)
    retornos = pd.DataFrame({"AAA": [0.01] * 5}, index=fechas)
    r = retorno_diario_cartera(retornos, {"AAA": 0.5, "SIN_DATOS": 0.5})
    assert np.allclose(r.values, 0.01)  # antes daba 0.005 (el faltante contaba como 0%)


# ---------------- CCL ----------------
def test_ccl_usa_la_mediana_de_los_pares():
    from core.data_providers import ccl_provider

    precios = {"GGAL.BA": 5000.0, "GGAL": 50.0, "YPFD.BA": 1050.0, "YPF": 1.0, "PAMP.BA": 4000.0, "PAM": 100.0}
    ccl_provider._ccl_cache = None
    with patch("core.data_providers.get_price", side_effect=lambda t, use_cache=True: precios.get(t)):
        resultado = ccl_provider.get_ccl_automatico(use_cache=False)
    # pares: 1000, 1050, 1000 -> mediana 1000
    assert resultado["valor"] == 1000.0
    assert "mediana" in resultado["fuente"]


def test_ccl_en_fecha_toma_el_ultimo_conocido():
    from core.data_providers.ccl_provider import ccl_en_fecha

    serie = pd.Series([1000.0, 1100.0], index=pd.to_datetime(["2024-01-02", "2024-01-05"]))
    assert ccl_en_fecha(serie, date(2024, 1, 4)) == 1000.0
    assert ccl_en_fecha(serie, date(2024, 1, 10)) == 1100.0
    assert ccl_en_fecha(serie, date(2023, 12, 1)) == 1000.0
    assert ccl_en_fecha(None, date(2024, 1, 1)) is None


# ---------------- Forecast ----------------
def test_vol_horizonte_es_el_promedio_cuadratico_del_camino():
    from core.forecasting.volatility_garch import vol_promedio_horizonte

    camino = pd.Series([0.30, 0.20], index=[1, 2])
    assert vol_promedio_horizonte(camino) == pytest.approx(np.sqrt((0.09 + 0.04) / 2))


def test_cono_acumula_varianzas_diarias():
    from core.forecasting.returns_forecast import cono_incertidumbre

    retornos = pd.Series([0.0] * 300, index=pd.bdate_range("2023-01-01", periods=300))
    camino = pd.Series([0.40, 0.10], index=[1, 2])  # vol que baja
    cono = cono_incertidumbre(retornos, camino, valor_actual=100.0)
    var_diaria = (camino / np.sqrt(252)) ** 2
    desvio_dia2 = np.sqrt(var_diaria.sum())
    assert cono.loc[2, "banda_68_sup"] == pytest.approx(100 * (1 + desvio_dia2))


# ---------------- Importación ----------------
def test_importar_usa_el_ratio_del_instrumento_ya_registrado(tmp_path):
    from core.importers.broker_movimientos import MovimientoCandidato
    from core.importers.import_service import importar_candidatos

    repo = _repo(tmp_path)
    repo.upsert_instrumento(
        Instrumento(ticker="GLOB", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="GLOB", ratio_cedear=2.0)
    )
    c = MovimientoCandidato(
        id_externo="x1", fecha=date(2024, 1, 1), ticker="GLOB", tipo_instrumento=TipoInstrumento.CEDEAR,
        ticker_usd="GLOB", ratio_cedear=None, accion=TransactionAction.COMPRA, cantidad=4, precio=1000.0,
        comision=0.0, moneda="ARS",
    )
    resumen = importar_candidatos([c], repo, usuario="fede")
    assert resumen.importados == 1
    assert resumen.completo


def test_importacion_incompleta_lo_informa(tmp_path):
    from core.importers.broker_movimientos import MovimientoCandidato
    from core.importers.import_service import importar_candidatos

    c = MovimientoCandidato(
        id_externo="x2", fecha=date(2024, 1, 1), ticker="NUEVO", tipo_instrumento=TipoInstrumento.CEDEAR,
        ticker_usd="NUEVO", ratio_cedear=None, accion=TransactionAction.COMPRA, cantidad=1, precio=10.0,
        comision=0.0, moneda="ARS",
    )
    resumen = importar_candidatos([c, c], _repo(tmp_path), usuario="fede")
    assert not resumen.completo
    assert resumen.pendientes_de_ratio == ["NUEVO"]  # sin repetidos


# ---------------- Cache de históricos ----------------
def test_get_history_cachea_y_no_vuelve_a_llamar_al_proveedor():
    from core import data_providers

    data_providers.limpiar_cache()
    df = pd.DataFrame({"AAA": [1.0, 2.0]}, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    with patch.object(data_providers._primary, "get_history", return_value=df) as mock:
        a = data_providers.get_history("AAA", period="1y")
        b = data_providers.get_history("AAA", period="1y")
    assert mock.call_count == 1
    a.iloc[0, 0] = 999  # devolver copias: modificar el resultado no corrompe el cache
    assert b.iloc[0, 0] == 1.0
    data_providers.limpiar_cache()
