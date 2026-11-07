"""
Tracker Quant — Data Finance. Punto de entrada único.
Correr con: streamlit run app.py

Usa st.navigation() (no la carpeta pages/ automágica) para poder:
  1) Controlar el orden real del sidebar (header de marca ARRIBA del menú).
  2) Definir el ícono de cada página como string en Python, no en el
     nombre del archivo -- evita el mojibake que rompía el menú cuando
     el proyecto se descomprimía en Windows con nombres de archivo emoji.
"""
import logging

import streamlit as st

import app_style
from app_helpers import configurar_almacen
from config.logging_config import setup_logging
from config.settings import settings
from core.auth.auth_service import render_login, render_logout_button
from core.storage import get_backend_status, reset_repository_cache

setup_logging()

st.set_page_config(
    page_title="Data Finance · Tracker Quant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
app_style.inject(st)

# ---------------- Sin sesión: pantalla de login ----------------
def _pantalla_login() -> None:
    with st.sidebar:
        app_style.sidebar_header(st)
    st.title("📊 Tracker Quant")
    st.caption("Data Finance · Risk Analytics — CCL, precios e históricos automatizados vía yfinance. Sistema cerrado.")
    render_login()


if not st.session_state.get("authentication_status"):
    # Navegación oculta con una sola página: sin esto Streamlit mostraba el menú
    # automático de la carpeta pages/ (todas las páginas) en la pantalla de login.
    st.navigation([st.Page(_pantalla_login, title="Ingresar", icon="🔑")], position="hidden").run()
    # El login (por cookie "recordarme" o por formulario) marca la sesión como autenticada
    # DURANTE esta corrida y no vuelve a correr el script: sin este rerun quedaba una pantalla
    # con solo el título hasta el próximo clic.
    if st.session_state.get("authentication_status"):
        st.rerun()
    st.stop()

username = st.session_state.get("name") or st.session_state.get("username", "usuario")

# ---------------- Con sesión: header de marca ARRIBA del menú ----------------
with st.sidebar:
    app_style.sidebar_header(st)
    st.markdown(f"👤 **{username}**")
    render_logout_button()
    st.divider()

# Menú por secciones, en el orden en que se usa: mirar → cargar → analizar → decidir → ajustar.
paginas = {
    "Resumen": [
        st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊", default=True),
        st.Page("pages/9_Reporte.py", title="Reporte", icon="📄"),
    ],
    "Mi cartera": [
        st.Page("pages/2_Cartera.py", title="Posiciones", icon="💼"),
        st.Page("pages/13_Evolucion.py", title="Evolución real", icon="📆"),
        st.Page("pages/3_Transacciones.py", title="Transacciones", icon="📝"),
        st.Page("pages/7_Importar_Broker.py", title="Importar del broker", icon="📥"),
    ],
    "Riesgo": [
        st.Page("pages/5_Riesgo.py", title="Riesgo", icon="🛡️"),
        st.Page("pages/6_Escenarios.py", title="Escenarios", icon="🕰️"),
        st.Page("pages/10_Forecasting.py", title="Forecasting", icon="🔮"),
        st.Page("pages/4_Historicos.py", title="Históricos", icon="📈"),
    ],
    "Decidir": [
        st.Page("pages/11_Candidatos.py", title="Candidatos", icon="🎯"),
    ],
    "Ajustes": [
        st.Page("pages/8_Configuracion.py", title="Configuración", icon="⚙️"),
        st.Page("pages/12_Estado.py", title="Estado del sistema", icon="🩺"),
    ],
}

pg = st.navigation(paginas, position="sidebar")

with st.sidebar:
    st.divider()
    app_style.sidebar_footer(st)
    estado_storage = get_backend_status()
    st.caption(f"Storage: `{estado_storage['activo']}` · Benchmark: `{settings.DEFAULT_BENCHMARK}`")

# ---------------- Alerta si Google Sheets no conectó (fallback silencioso a CSV) ----------------
if estado_storage["inconsistente"]:
    st.error(
        "🚨 **Los datos NO se están guardando en Google Sheets.** La app está usando CSV local, "
        "que en Streamlit Cloud se borra al reiniciar."
    )
    if estado_storage["error"]:
        st.code(estado_storage["error"], language="text")
    else:
        st.write(
            f"No hubo error de conexión: el backend pedido fue `{estado_storage['solicitado']}`. "
            "Revisá que `storage_backend = \"gsheets\"` esté como PRIMERA línea de los Secrets, "
            "fuera de cualquier [tabla]."
        )
    if st.button("🔄 Reintentar conexión a Google Sheets"):
        reset_repository_cache()
        st.rerun()

configurar_almacen()

# Si una página falla, se muestra el error y el resto de la app sigue andando
# (antes una excepción dejaba la pantalla a medio dibujar). st.stop / st.rerun
# no se capturan acá: heredan de BaseException, no de Exception.
try:
    pg.run()
except Exception as exc:  # noqa: BLE001
    logging.getLogger("app").exception("Error en la página %s", pg.title)
    st.error(
        f"😵 La página **{pg.title}** falló al cargar. Las otras páginas siguen andando: "
        "probá recargar o mirá **Estado del sistema** (Yahoo o Google Sheets pueden estar caídos)."
    )
    with st.expander("Detalle técnico (para pasárselo a quien mantenga la app)"):
        st.exception(exc)