"""ETL diario: universo, carga en el almacén, protección contra corridas pobres y snapshot."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from config.settings import settings
from core import data_providers
from core.etl import precios as etl
from core.storage.csv_repository import CsvRepository
from core.storage.models import Instrumento, PrecioCierre, TipoInstrumento, Transaction, TransactionAction, WatchlistItem


def _serie(ticker, dias=1300):
    rng = np.random.default_rng(abs(hash(ticker)) % 2**32)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=dias)
    base = 1500.0 if ticker.endswith(".BA") else 100.0
    return pd.DataFrame({ticker: base * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))))}, index=idx)


class Proveedor:
    name = "fake"
    ultimo_error = None
    rate_limit = False

    def __init__(self, sin_datos=()):
        self.sin_datos = set(sin_datos)
        self.lotes = []

    def get_history_lote(self, tickers, period="2y"):
        self.lotes.append((tuple(tickers), period))
        return {t: _serie(t) for t in tickers if t not in self.sin_datos}

    def get_history(self, ticker, period="2y"):
        return None if ticker in self.sin_datos else _serie(ticker)

    def get_price(self, ticker):
        return None if ticker in self.sin_datos else float(_serie(ticker)[ticker].iloc[-1])

    def get_info(self, ticker):
        return {}


@pytest.fixture
def repo(tmp_path):
    r = CsvRepository(
        transactions_file=tmp_path / "t.csv", audit_file=tmp_path / "a.csv", snapshots_file=tmp_path / "s.csv",
        instrumentos_file=tmp_path / "i.csv", processed_files_file=tmp_path / "p.csv", forecasts_file=tmp_path / "f.csv",
    )
    r.upsert_instrumento(Instrumento(ticker="AAPL", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="AAPL", ratio_cedear=20))
    r.add_transactions([
        Transaction(fecha=date.today() - timedelta(days=300), ticker="AAPL", accion=TransactionAction.COMPRA, cantidad=10, precio=15000),
        Transaction(fecha=date.today() - timedelta(days=300), ticker="GGAL", accion=TransactionAction.COMPRA, cantidad=100, precio=4000),
    ])
    r.upsert_watchlist_item(WatchlistItem(ticker="MSFT", ticker_usd="MSFT", ratio_cedear=30))
    return r


def test_universo(repo):
    u = etl.universo(repo)
    # ADR del CEDEAR, .BA de la acción sin instrumento cargado, watchlist, benchmark y pares del CCL
    for t in ["AAPL", "AAPL.BA", "GGAL.BA", "MSFT", settings.DEFAULT_BENCHMARK, "BMA.BA", "PAM"]:
        assert t in u


def test_periodo_base_cubre_la_primera_transaccion(repo):
    assert etl.periodo_base(repo) == settings.HISTORY_PERIOD_BASE
    repo.add_transactions([Transaction(fecha=date.today() - timedelta(days=4 * 365), ticker="GGAL",
                                       accion=TransactionAction.COMPRA, cantidad=1, precio=100)])
    assert etl.periodo_base(repo) == "5y"


def test_corrida_completa_guarda_precios_snapshot_y_auditoria(repo, monkeypatch):
    prov = Proveedor()
    monkeypatch.setattr(data_providers, "_primary", prov)
    r = etl.correr(repo, hoy=date.today())
    assert r.ok, r.error
    guardados = {p.ticker for p in repo.list_precios()}
    assert set(r.tickers_esperados) == guardados
    assert r.filas == len(repo.list_precios())
    assert r.snapshot.startswith("guardado")
    assert len(repo.list_snapshots()) == 1
    assert repo.list_audit_events()[0].accion == "ETL_PRECIOS"
    assert etl.ultima_corrida(repo) is not None
    # Los pares del CCL con 5 años; el resto con la ventana base, en lotes separados.
    periodos = {p for _, p in prov.lotes}
    assert {etl.PERIODO_CCL, settings.HISTORY_PERIOD_BASE} <= periodos


def test_segunda_corrida_del_dia_no_duplica_el_snapshot(repo, monkeypatch):
    monkeypatch.setattr(data_providers, "_primary", Proveedor())
    etl.correr(repo)
    r = etl.correr(repo)
    assert r.snapshot == "ya había uno de hoy"
    assert len(repo.list_snapshots()) == 1


def test_dry_run_no_escribe(repo, monkeypatch):
    monkeypatch.setattr(data_providers, "_primary", Proveedor())
    r = etl.correr(repo, escribir=False)
    assert r.ok and r.filas > 0
    assert repo.list_precios() == [] and repo.list_snapshots() == [] and repo.list_audit_events() == []


def test_corrida_pobre_no_pisa_el_almacen(repo, monkeypatch):
    anteriores = [PrecioCierre(fecha=date(2026, 1, 1), ticker=f"T{i}", close=1.0) for i in range(40)]
    repo.reemplazar_precios(anteriores)
    monkeypatch.setattr(data_providers, "_primary", Proveedor())  # trae ~11 tickers < 50% de 40
    r = etl.correr(repo, con_snapshot=False)
    assert not r.ok and "no se pisa" in r.error
    assert len(repo.list_precios()) == 40


def test_yahoo_sin_nada_falla(repo, monkeypatch):
    prov = Proveedor()
    monkeypatch.setattr(data_providers, "_primary", prov)
    prov.sin_datos = set(etl.universo(repo))
    r = etl.correr(repo, con_snapshot=False)
    assert not r.ok and r.problemas
    assert repo.list_precios() == []


def test_la_app_lee_lo_que_guardo_el_etl_sin_volver_a_bajar_la_historia(repo, monkeypatch):
    monkeypatch.setattr(data_providers, "_primary", Proveedor())
    etl.correr(repo, con_snapshot=False)

    prov_app = Proveedor()
    monkeypatch.setattr(data_providers, "_primary", prov_app)
    data_providers.limpiar_cache()
    data_providers.almacen.configurar(repo.list_precios)
    data_providers.precargar(["AAPL", "SPY"], "2y")
    assert prov_app.lotes == [(("AAPL", "SPY"), data_providers.PERIODO_COMPLETAR)]
    assert len(data_providers.get_history("AAPL", "2y")) > 400
