import streamlit as st

from app_helpers import obtener_cartera_actual, obtener_historicos_riesgo, require_login
from core.viz import charts

username = require_login()

st.title("📈 Históricos de Precios (USD equivalente)")
st.caption(
    "Precios usados en todos los cálculos de riesgo: CEDEARs vía su ADR, acciones argentinas "
    "directas convertidas día por día con el CCL histórico. Todo en la misma moneda para que sea comparable. "
    "Fuente: yfinance, con Alpha Vantage como respaldo."
)

posiciones = obtener_cartera_actual()
if not posiciones:
    st.info("Todavía no cargaste ninguna transacción.")
    st.stop()

periodo = st.selectbox("Período", ["6mo", "1y", "2y", "5y"], index=2)
historicos = obtener_historicos_riesgo(posiciones, period=periodo)

if historicos.empty:
    st.warning("No se pudo obtener histórico de precios en este momento.")
    st.stop()

st.markdown("##### Evolución de precios (normalizado, base 100)")
normalizado = historicos.dropna() / historicos.dropna().iloc[0] * 100
st.plotly_chart(charts.linea_multi(normalizado), width="stretch")

st.divider()
st.subheader("Tabla de precios en USD equivalente (últimos 30 días con datos)")
st.dataframe(historicos.dropna(how="all").tail(30).sort_index(ascending=False), width="stretch")

st.caption(
    f"{len(historicos.dropna(how='all'))} días con datos disponibles en el período seleccionado. "
    "Los días sin cotización (feriados de un mercado y no del otro) se completan hacia adelante "
    "(forward-fill) para poder calcular retornos de forma consistente."
)
