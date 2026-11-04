"""Estado del sistema: para saber qué falla sin entrar a los logs de Streamlit Cloud."""
from datetime import date, datetime

import pandas as pd
import streamlit as st

from app_helpers import invalidar_caches, require_login
from core import data_providers
from core.etl.precios import ultima_corrida
from core.sistema import version_deploy, versiones_paquetes
from core.storage import get_backend_status, get_repository

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

# ---------------- Almacén de precios (ETL diario) ----------------
st.subheader("Almacén de precios (ETL diario)")
alm = data_providers.almacen.estado()
if alm["error"]:
    st.error(f"🔴 No se pudo leer la pestaña `precios`: `{alm['error']}`. Se usa Yahoo directo.")
elif not alm["tickers"]:
    st.warning(
        "🟡 El almacén está vacío: todavía no corrió el ETL (GitHub Actions → *ETL diario* → Run workflow). "
        "Mientras tanto todo se baja de Yahoo en cada visita, que es más lento."
    )
else:
    ruedas = len(pd.bdate_range(alm["ultima_fecha"], date.today())) - 1
    texto = (
        f"{alm['tickers']} tickers, último cierre del **{alm['ultima_fecha']:%d/%m/%Y}**"
        + (f" · actualizado {alm['actualizado_en']:%d/%m %H:%M} UTC" if alm["actualizado_en"] else "")
    )
    if ruedas > 2:
        st.warning(f"🟡 {texto}. Tiene {ruedas} ruedas de atraso: revisá que el ETL esté corriendo en GitHub Actions.")
    else:
        st.success(f"🟢 {texto}. Los días posteriores se completan en vivo desde Yahoo.")

corrida = ultima_corrida(get_repository())
if corrida:
    severo = "FALLÓ" in corrida.detalle
    (st.error if severo else st.caption)(
        f"Última corrida del ETL ({corrida.timestamp:%d/%m/%Y %H:%M} UTC): {corrida.detalle}"
    )
else:
    st.caption("Sin corridas del ETL registradas en el log de auditoría.")

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
