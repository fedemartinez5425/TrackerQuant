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
from core.portfolio.historicos import (
    InstrumentoRiesgo,
    alinear_dias_comunes,
    desde_posiciones,
    historicos_usd_equivalente,
)
from core.portfolio.portfolio_engine import construir_cartera
from core.storage import get_repository
from core.storage.models import Instrumento, TipoInstrumento, Transaction, WatchlistItem


def require_login() -> str:
    """Verifica que haya sesión activa. El header de marca, el usuario y el
    botón de logout ya se renderizan una sola vez en app.py (arriba del
    menú de navegación) -- esta función solo confirma la sesión y aplica
    el CSS global, por si alguna página se abre de forma directa.

    Devuelve el USERNAME (identificador único, ej. "fede"), que es lo que
    se guarda en el registro de auditoría -- no el nombre para mostrar,
    que puede repetirse o cambiar."""
    app_style.inject(st)
    if not st.session_state.get("authentication_status"):
        st.warning("Necesitás iniciar sesión para ver esta página.")
        st.page_link("app.py", label="⬅️ Ir al login", icon="🔑")
        st.stop()
    return st.session_state.get("username") or st.session_state.get("name") or "usuario"


def invalidar_caches() -> None:
    """Llamar después de cualquier escritura (alta, reverso, importación)
    para que todas las páginas vean el dato nuevo."""
    st.cache_data.clear()
    data_providers.limpiar_cache()


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


@st.cache_data(ttl=settings.PRICE_CACHE_TTL_SECONDS, show_spinner="Trayendo históricos de precios...")
def _cached_historicos_usd(instrumentos: tuple, period: str) -> pd.DataFrame:
    return historicos_usd_equivalente(list(instrumentos), period=period)


def obtener_historicos_riesgo(posiciones, period: str | None = None) -> pd.DataFrame:
    """Históricos en USD equivalente para TODAS las posiciones (mezclando
    CEDEAR y acciones argentinas directas correctamente vía CCL histórico),
    más el benchmark, alineados SOLO en los días en que cotizaron todos
    (ver core/portfolio/historicos.alinear_dias_comunes). Cacheado: antes se
    volvía a bajar todo en cada clic."""
    period = period or settings.HISTORY_PERIOD
    instrumentos = tuple(sorted(desde_posiciones(posiciones)))
    historicos_posiciones = _cached_historicos_usd(instrumentos, period)
    historico_benchmark = obtener_historicos([settings.DEFAULT_BENCHMARK], period=period)
    if historicos_posiciones.empty:
        return alinear_dias_comunes(historico_benchmark)
    if historico_benchmark.empty:
        return alinear_dias_comunes(historicos_posiciones)
    combinado = pd.concat([historicos_posiciones, historico_benchmark], axis=1)
    return alinear_dias_comunes(combinado)


def obtener_watchlist() -> list[WatchlistItem]:
    return get_repository().list_watchlist()


def obtener_historicos_decision(posiciones, watchlist: list[WatchlistItem]) -> pd.DataFrame:
    """Históricos en USD equivalente de tenencias + watchlist con
    HISTORY_PERIOD_DECISION. SIN alinear: cada candidato se cruza con la
    cartera en sus propios días comunes (ver core/decision/candidatos.py)."""
    # Por ticker: si un candidato ya está en cartera, manda la definición de la tenencia.
    instrumentos = {i.ticker: InstrumentoRiesgo(i.ticker, i.tipo_instrumento, i.ticker_usd) for i in watchlist}
    instrumentos.update({i.ticker: i for i in desde_posiciones(posiciones)})
    if not instrumentos:
        return pd.DataFrame()
    return _cached_historicos_usd(tuple(sorted(instrumentos.values())), settings.HISTORY_PERIOD_DECISION)


@st.cache_data(ttl=settings.PRICE_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_precio_unidad(ticker: str, tipo: str, ticker_usd: str | None, ratio: float | None, ccl: float | None):
    from core.decision.candidatos import precio_unidad_ars

    item = WatchlistItem.model_construct(
        ticker=ticker, tipo_instrumento=TipoInstrumento(tipo), ticker_usd=ticker_usd, ratio_cedear=ratio
    )
    return precio_unidad_ars(item, ccl=ccl)


def obtener_precio_unidad(item: WatchlistItem) -> float | None:
    """Precio de 1 unidad en ARS (cacheado), con el CCL automático de hoy."""
    ccl = _cached_ccl()
    return _cached_precio_unidad(
        item.ticker, item.tipo_instrumento.value, item.ticker_usd, item.ratio_cedear, ccl["valor"] if ccl else None
    )


def avisar_excluidos(historicos: pd.DataFrame) -> None:
    """Si algún activo quedó fuera del cálculo de riesgo por tener muy poca
    historia, lo dice en pantalla (en vez de que el número cambie en silencio)."""
    excluidos = historicos.attrs.get("excluidos") if historicos is not None else None
    if excluidos:
        st.caption(
            f"⚠️ Sin historia suficiente para el cálculo de riesgo (excluidos, su peso se reparte "
            f"entre el resto): {', '.join(excluidos)}."
        )


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
