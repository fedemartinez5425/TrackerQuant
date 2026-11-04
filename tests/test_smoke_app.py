"""
Smoke test: levanta el login y TODAS las páginas con Streamlit AppTest, con
una cartera de prueba en CSV temporal y precios sintéticos (sin red).
Si algo rompe el arranque de una página, falla acá (y en CI) antes de llegar
a producción.
"""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core import data_providers
from core.storage.models import Instrumento, TipoInstrumento, Transaction, TransactionAction, WatchlistItem

RAIZ = Path(__file__).resolve().parent.parent
PAGINAS = sorted(p.name for p in (RAIZ / "pages").glob("*.py"))
TIMEOUT = 60


def _serie(ticker: str, dias: int = 1200) -> pd.DataFrame:
    rng = np.random.default_rng(abs(hash(ticker)) % 2**32)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=dias)
    base = 1500.0 if ticker.endswith(".BA") else 100.0
    precios = base * np.exp(np.cumsum(rng.normal(0.0003, 0.015, len(idx))))
    return pd.DataFrame({ticker: precios}, index=idx)


class ProveedorSintetico:
    name = "sintetico"
    ultimo_error = None
    rate_limit = False

    def get_price(self, ticker):
        return float(_serie(ticker)[ticker].iloc[-1])

    def get_history(self, ticker, period="2y"):
        return _serie(ticker)

    def get_history_lote(self, tickers, period="2y"):
        return {t: _serie(t) for t in tickers}

    def get_info(self, ticker):
        return {}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    from config.settings import settings
    import core.storage as storage

    for nombre in ("TRANSACTIONS", "AUDIT_LOG", "SNAPSHOTS", "INSTRUMENTOS", "PROCESSED_FILES", "FORECASTS", "WATCHLIST"):
        monkeypatch.setattr(settings, f"{nombre}_FILE", tmp_path / f"{nombre.lower()}.csv")
    # Nunca Google Sheets en tests, aunque haya secrets locales.
    monkeypatch.setattr(storage, "get_secret", lambda ruta, default=None: "csv" if ruta == ["storage_backend"] else default)
    storage.reset_repository_cache()
    monkeypatch.setattr(data_providers, "_primary", ProveedorSintetico())

    repo = storage.get_repository()
    repo.upsert_instrumento(Instrumento(ticker="AAPL", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="AAPL", ratio_cedear=20))
    repo.upsert_instrumento(Instrumento(ticker="GGAL", tipo_instrumento=TipoInstrumento.ACCION_ARG))
    hace = date.today() - timedelta(days=400)
    repo.add_transactions([
        Transaction(fecha=hace, ticker="AAPL", accion=TransactionAction.COMPRA, cantidad=50, precio=15000),
        Transaction(fecha=hace, ticker="GGAL", accion=TransactionAction.COMPRA, cantidad=100, precio=4000),
        Transaction(fecha=date.today() - timedelta(days=1), ticker="AAPL", accion=TransactionAction.COMPRA, cantidad=10, precio=17000),
    ])
    repo.upsert_watchlist_item(WatchlistItem(ticker="MSFT", ticker_usd="MSFT", ratio_cedear=30))
    yield
    storage.reset_repository_cache()


def _logueado(at: AppTest) -> AppTest:
    at.session_state["authentication_status"] = True
    at.session_state["username"] = "test"
    at.session_state["name"] = "Test"
    return at


def test_login_arranca_sin_errores(entorno):
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=TIMEOUT).run()
    assert not at.exception
    assert any("Tracker Quant" in t.value for t in at.title)


def test_app_logueada_muestra_el_dashboard(entorno):
    at = _logueado(AppTest.from_file(str(RAIZ / "app.py"), default_timeout=TIMEOUT)).run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert len(at.metric) >= 6, "el Dashboard no dibujó los KPIs"


@pytest.mark.parametrize("pagina", PAGINAS)
def test_cada_pagina_carga_sin_excepciones(entorno, pagina):
    # Desde app.py: st.page_link / st.switch_page necesitan el st.navigation de la app.
    at = _logueado(AppTest.from_file(str(RAIZ / "app.py"), default_timeout=TIMEOUT)).run()
    at.switch_page(f"pages/{pagina}").run()
    assert not at.exception, f"{pagina}: {[e.value for e in at.exception]}"
    # El aislador de errores de app.py convierte una excepción en st.error: también cuenta.
    fallas = [e.value for e in at.error if "falló al cargar" in e.value]
    assert not fallas, f"{pagina}: {fallas}"


@pytest.mark.parametrize("pagina", ["1_Dashboard.py", "12_Estado.py", "11_Candidatos.py"])
def test_paginas_con_el_almacen_cargado_por_el_etl(entorno, pagina):
    from core.etl.precios import correr
    from core.storage import get_repository

    assert correr(get_repository(), con_snapshot=False).ok
    data_providers.limpiar_cache()
    at = _logueado(AppTest.from_file(str(RAIZ / "app.py"), default_timeout=TIMEOUT)).run()
    at.switch_page(f"pages/{pagina}").run()
    assert not at.exception, f"{pagina}: {[e.value for e in at.exception]}"
    assert not [e.value for e in at.error if "falló al cargar" in e.value]
    assert data_providers.almacen.estado()["tickers"] > 0
