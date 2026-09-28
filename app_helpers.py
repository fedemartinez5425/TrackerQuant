"""
Funciones compartidas por todas las páginas de pages/*.
Vive en la raíz (no en core/) porque depende de Streamlit.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import app_style
from config.settings import settings
from core import data_providers
from core.portfolio.historicos import desde_posiciones, historicos_usd_equivalente
from core.portfolio.portfolio_engine import construir_cartera
from core.storage import get_repository
from core.storage.models import Instrumento, Transaction


def require_login() -> str:
    """Verifica que haya sesión activa. El header de marca, el usuario y el
    botón de logout ya se renderizan una sola vez en app.py (arriba del
    menú de navegación) -- esta función solo confirma la sesión y aplica
    el CSS global, por si alguna página se abre de forma directa."""
    app_style.inject(st)
    if not st.session_state.get("authentication_status"):
        st.warning("Necesitás iniciar sesión para ver esta página.")
        st.page_link("app.py", label="⬅️ Ir al login", icon="🔑")
        st.stop()
    return st.session_state.get("name") or st.session_state.get("username", "usuario")


@st.cache_data(ttl=settings.PRICE_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_history(tickers: tuple[str, ...], period: str) -> pd.DataFrame:
    return data_providers.get_history_multi(list(tickers), period=period)


@st.cache_data(ttl=settings.PRICE_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_ccl() -> dict | None:
    from core.data_providers.ccl_provider import get_ccl_automatico

    return get_ccl_automatico(use_cache=False)  # el cache lo maneja st.cache_data acá


def obtener_transacciones() -> list[Transaction]:
    repo = get_repository()
    return repo.list_transactions()


def obtener_instrumentos() -> dict[str, Instrumento]:
    """Tabla dimensión completa, indexada por ticker (una sola consulta al
    repositorio, reusada por todas las páginas que arman la cartera)."""
    repo = get_repository()
    return {inst.ticker: inst for inst in repo.list_instrumentos()}


def obtener_cartera_actual():
    transacciones = obtener_transacciones()
    instrumentos = obtener_instrumentos()
    return construir_cartera(transacciones, instrumentos)


def obtener_historicos(tickers: list[str], period: str | None = None) -> pd.DataFrame:
    period = period or settings.HISTORY_PERIOD
    if not tickers:
        return pd.DataFrame()
    return _cached_history(tuple(sorted(set(tickers))), period)


def obtener_historicos_riesgo(posiciones, period: str | None = None) -> pd.DataFrame:
    """Históricos en USD equivalente para TODAS las posiciones (mezclando
    CEDEAR y acciones argentinas directas correctamente vía CCL histórico),
    más el benchmark, todo alineado en el mismo DataFrame."""
    period = period or settings.HISTORY_PERIOD
    instrumentos = desde_posiciones(posiciones)
    historicos_posiciones = historicos_usd_equivalente(instrumentos, period=period)
    historico_benchmark = obtener_historicos([settings.DEFAULT_BENCHMARK], period=period)
    if historicos_posiciones.empty:
        return historico_benchmark
    if historico_benchmark.empty:
        return historicos_posiciones
    combinado = pd.concat([historicos_posiciones, historico_benchmark], axis=1)
    return combinado.ffill().dropna(how="all")


def formato_moneda(valor: float | None, moneda: str = "ARS") -> str:
    if valor is None:
        return "—"
    simbolo = "US$" if moneda == "USD" else "$"
    return f"{simbolo} {valor:,.2f}"


def formato_pct(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"{valor * 100:,.2f}%"


def mostrar_ccl_sidebar() -> None:
    with st.sidebar:
        ccl = _cached_ccl()
        if ccl:
            st.metric("CCL (automático)", f"$ {ccl['valor']:,.2f}")
            st.caption(f"Fuente: {ccl['fuente']}")
        else:
            st.caption("CCL no disponible en este momento (falló el cálculo automático).")
