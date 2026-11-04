"""Estado del sistema: para saber qué falla sin entrar a los logs de Streamlit Cloud."""
from datetime import datetime

import streamlit as st

from app_helpers import invalidar_caches, require_login
from core import data_providers
from core.sistema import version_deploy, versiones_paquetes
from core.storage import get_backend_status

require_login()

st.title("🩺 Estado del sistema")
st.caption("Si la app anda lenta o no trae precios, empezá por acá.")


def _hace(ts: float | None) -> str:
    if not ts:
        return "nunca (desde que arrancó la app)"
    segundos = int(datetime.now().timestamp() - ts)
    if segundos < 60:
        return f"hace {segundos} s"
    if segundos < 3600:
        return f"hace {segundos // 60} min"
    return f"hace {segundos // 3600} h {segundos % 3600 // 60} min"


# ---------------- Storage ----------------
st.subheader("Datos guardados (storage)")
storage = get_backend_status()
if storage["inconsistente"]:
    st.error(f"🔴 Se pidió Google Sheets pero está usando CSV local. Motivo: `{storage['error'] or 'sin detalle'}`")
elif storage["activo"] == "gsheets":
    st.success("🟢 Google Sheets conectado.")
else:
    st.info("🔵 CSV local (modo desarrollo).")

# ---------------- Yahoo ----------------
st.subheader("Precios de mercado (Yahoo Finance)")
estado = data_providers.estado_proveedores()
if estado["yahoo_disponible"]:
    st.success(f"🟢 Yahoo responde. Última respuesta OK: {_hace(estado['ultimo_exito'])}.")
else:
    st.error(
        f"🔴 Yahoo en pausa por {estado['pausa_restante_segundos']} s más (falló o limitó las requests). "
        "Mientras tanto se usan los últimos precios en memoria."
    )
if estado["ultimo_error"]:
    st.caption(f"Último error: `{estado['ultimo_error']}`")
st.caption(
    f"Tickers con historia en memoria: {estado['tickers_en_memoria']} · "
    f"Alpha Vantage de respaldo: {'configurado' if estado['alpha_vantage_configurado'] else 'sin API key'}."
)

c1, c2 = st.columns(2)
if c1.button("Probar Yahoo ahora", help="Baja el precio de SPY sin usar el cache."):
    with st.spinner("Consultando Yahoo…"):
        precio = data_providers.get_price("SPY", use_cache=False)
    if precio:
        st.toast(f"Yahoo OK: SPY a US$ {precio:,.2f}", icon="✅")
    else:
        st.toast("Yahoo no respondió.", icon="⚠️")
    st.rerun()
if c2.button("Vaciar caches", help="Vuelve a leer transacciones y precios desde cero."):
    invalidar_caches()
    st.toast("Caches vaciados.", icon="🧹")

# ---------------- Versión ----------------
st.subheader("Versión deployada")
version = version_deploy()
if version:
    st.write(f"Rama `{version['rama'] or '—'}` · commit `{version['commit'] or '—'}`")
else:
    st.write("Sin información de git en este entorno.")
st.dataframe(
    [{"Paquete": k, "Versión": v} for k, v in versiones_paquetes().items()],
    hide_index=True,
    width="content",
)
st.caption(
    "Estas versiones deben coincidir con requirements.txt. Si no coinciden, Streamlit Cloud "
    "instaló otra cosa: hacé Reboot desde share.streamlit.io."
)
