"""
Tracker Quant — Data Finance. Punto de entrada único.
Correr con: streamlit run app.py

Usa st.navigation() (no la carpeta pages/ automágica) para poder:
  1) Controlar el orden real del sidebar (header de marca ARRIBA del menú).
  2) Definir el ícono de cada página como string en Python, no en el
     nombre del archivo -- evita el mojibake que rompía el menú cuando
     el proyecto se descomprimía en Windows con nombres de archivo emoji.
"""
import streamlit as st

import app_style
from config.logging_config import setup_logging
from config.settings import settings
from core.auth.auth_service import render_login, render_logout_button

setup_logging()

st.set_page_config(
    page_title="Data Finance · Tracker Quant",
    page_icon="⚠️",
    layout="wide",
    initial_sidebar_state="expanded",
)
app_style.inject(st)

# ---------------- Sin sesión: pantalla de login ----------------
if not st.session_state.get("authentication_status"):
    with st.sidebar:
        app_style.sidebar_header(st)
    st.title("⚠️ Tracker Quant")
    st.caption("Data Finance · Risk Analytics — CCL, precios e históricos automatizados vía yfinance. Sistema cerrado.")
    render_login()
    st.stop()

username = st.session_state.get("name") or st.session_state.get("username", "usuario")

# ---------------- Con sesión: header de marca ARRIBA del menú ----------------
with st.sidebar:
    app_style.sidebar_header(st)
    st.markdown(f"👤 **{username}**")
    render_logout_button()
    st.divider()

paginas = [
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊", default=True),
    st.Page("pages/9_Reporte.py", title="Reporte", icon="📄"),
    st.Page("pages/2_Cartera.py", title="Cartera", icon="💼"),
    st.Page("pages/3_Transacciones.py", title="Transacciones", icon="📝"),
    st.Page("pages/4_Historicos.py", title="Históricos", icon="📈"),
    st.Page("pages/5_Riesgo.py", title="Riesgo", icon="⚠️"),
    st.Page("pages/10_Forecasting.py", title="Forecasting", icon="🔮"),
    st.Page("pages/6_Escenarios.py", title="Escenarios", icon="🕰️"),
    st.Page("pages/7_Importar_Broker.py", title="Importar Broker", icon="📥"),
    st.Page("pages/8_Configuracion.py", title="Configuración", icon="⚙️"),
]

with st.sidebar:
    st.markdown(
        "<div style='font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;"
        "color:#7C9089;margin:0 0 4px 2px;'>Módulos</div>",
        unsafe_allow_html=True,
    )

pg = st.navigation(paginas, position="sidebar")

with st.sidebar:
    st.divider()
    app_style.sidebar_footer(st)
    st.caption(f"Storage: `{settings.STORAGE_BACKEND}` · Benchmark: `{settings.DEFAULT_BENCHMARK}`")

pg.run()
