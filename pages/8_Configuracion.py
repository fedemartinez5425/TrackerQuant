import pandas as pd
import streamlit as st

from app_helpers import require_login
from config.settings import settings
from core.cloud_secrets import get_secret
from core.data_providers.comafi_ratios import actualizar_cache, leer_cache
from core.storage import get_repository

username = require_login()

st.title("⚙️ Configuración")

st.subheader("Storage backend")
st.write(f"Backend activo: **`{settings.STORAGE_BACKEND}`**")
st.markdown(
    """
Por defecto la app guarda todo en CSV local (`/data`), así funciona sin configurar nada
mientras armás la planilla.

**El objetivo de este proyecto es usar Google Sheets como log de transacciones y de
snapshots históricos**, para poder después analizar la evolución real del riesgo.
Para activarlo:
1. Creá una cuenta de servicio en Google Cloud con la API de Google Sheets habilitada.
2. Descargá el JSON de credenciales y guardalo en `config/service_account.json`.
3. Creá una planilla de Google Sheets nueva (o usá una existente) y compartila con el
   email de la cuenta de servicio (como Editor).
4. En el archivo `.env` (raíz del proyecto), seteá:
   ```
   STORAGE_BACKEND=gsheets
   GOOGLE_SHEETS_SPREADSHEET_ID=<el ID de tu planilla>
   ```
5. Reiniciá la app. Las pestañas `transactions`, `audit_log` y `portfolio_snapshots` se
   crean solas la primera vez.

Si algo de esto falla, la app cae automáticamente a CSV local (nunca se rompe por falta
de configuración de Google).
    """
)

st.divider()
st.subheader("Ratios de CEDEAR (fuente: Comafi)")
st.markdown(
    "En vez de hardcodear los ratios, se bajan del [listado oficial de Comafi]"
    "(https://www.comafi.com.ar/custodiaglobal/programas.aspx). Actualizalo de tanto en "
    "tanto (los ratios cambian por ampliaciones de capital o splits)."
)
if st.button("🔄 Actualizar ratios desde Comafi"):
    with st.spinner("Descargando y parseando el listado de Comafi..."):
        df_ratios, error = actualizar_cache(settings.CEDEAR_RATIOS_FILE)
    if error:
        st.warning(error)
    else:
        st.success(f"Ratios actualizados: {len(df_ratios)} instrumentos encontrados.")

df_cache = leer_cache(settings.CEDEAR_RATIOS_FILE)
if df_cache.empty:
    st.info("Todavía no hay ratios en cache. Presioná el botón de arriba para bajarlos.")
else:
    st.caption(f"{len(df_cache)} instrumentos en cache. Revisá que el ticker que usás esté bien mapeado:")
    filtro = st.text_input("Filtrar por ticker", "").upper().strip()
    df_mostrar = df_cache[df_cache["ticker"].str.contains(filtro)] if filtro else df_cache
    st.dataframe(df_mostrar, width="stretch", hide_index=True)

st.divider()
st.subheader("CCL automático")
st.markdown(
    "El dólar CCL no se carga a mano: se calcula con el precio de un CEDEAR líquido "
    "en pesos contra su ADR en dólares (y también se usa una versión histórica día por día "
    "para convertir tus acciones argentinas directas a USD equivalente en los cálculos de riesgo)."
)
df_pares = pd.DataFrame(settings.CCL_PARES, columns=["Ticker BCBA", "Ticker ADR", "Ratio"])
st.dataframe(df_pares, hide_index=True, width="stretch")
st.caption(
    "Se prueban en orden hasta encontrar uno con datos. Los ratios son de referencia — "
    "confirmalos contra BYMA o tu broker y ajustalos en `config/settings.py` (`CCL_PARES`) si hace falta."
)

st.divider()
st.subheader("Parámetros de riesgo")
col1, col2 = st.columns(2)
col1.write(f"**Benchmark por defecto:** {settings.DEFAULT_BENCHMARK}")
col1.write(f"**Período histórico:** {settings.HISTORY_PERIOD}")
col2.write(f"**Cache de precios/CCL:** {settings.PRICE_CACHE_TTL_SECONDS}s")
col2.write(f"**Escenarios de estrés:** {', '.join(f'{s:.0%}' for s in settings.STRESS_SCENARIOS)}")
st.caption("Estos valores se cambian en el archivo `.env` o en `config/settings.py`.")

st.divider()
st.subheader("Usuarios")
st.markdown(
    """
Sistema cerrado: no hay registro público. Para agregar o cambiar un usuario, corré desde
la terminal (en la raíz del proyecto):

```bash
python scripts/generar_credenciales.py
```
    """
)

st.divider()
st.subheader("🔄 Sincronización automática con Google Drive")
st.markdown(
    """
En vez de subir el CSV del broker a mano cada vez, dejalo en una carpeta de
Google Drive (podés automatizar ese paso con un filtro de Gmail que
reenvíe el adjunto del broker a esa carpeta — gratis, sin código) y la app
detecta los archivos nuevos, los tipifica mirando las columnas del CSV
(no el nombre del archivo), y te deja importarlos con un click.

**Configuración** (en `.env` o en `st.secrets` si está en Streamlit Cloud):
```
DRIVE_FOLDER_ID=<ID de la carpeta de Drive>
```
Usa las mismas credenciales de service account que Google Sheets — solo
hace falta compartir esa carpeta de Drive con el mismo email de la cuenta
de servicio (como Lector alcanza).
    """
)

drive_folder_id = get_secret(["drive_folder_id"], settings.DRIVE_FOLDER_ID)

if not drive_folder_id:
    st.info("Configurá `DRIVE_FOLDER_ID` para activar esta sección.")
else:
    if st.button("🔍 Buscar archivos nuevos en Drive"):
        try:
            from core.importers.drive_sync import archivos_pendientes

            credentials_info = get_secret(["gcp_service_account"])
            credentials_info = dict(credentials_info) if credentials_info else None
            service_account_file = None if credentials_info else settings.GOOGLE_SERVICE_ACCOUNT_FILE

            with st.spinner("Consultando Google Drive..."):
                pendientes = archivos_pendientes(drive_folder_id, repo, credentials_info, service_account_file)
            st.session_state["drive_pendientes"] = pendientes
            if not pendientes:
                st.success("No hay archivos nuevos — ya importaste todo lo que hay en la carpeta.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"No se pudo conectar a Google Drive: {exc}")

    pendientes = st.session_state.get("drive_pendientes", [])
    if pendientes:
        st.write(f"**{len(pendientes)} archivo(s) nuevo(s) encontrado(s):**")
        for archivo in pendientes:
            with st.expander(f"📄 {archivo['name']} (modificado: {archivo.get('modifiedTime', '—')})"):
                if st.button("Analizar y traer", key=f"drive_{archivo['id']}"):
                    from core.importers.drive_sync import descargar_contenido, detectar_tipo_archivo
                    from core.importers.broker_movimientos import parsear_movimientos_csv
                    from core.importers.import_service import importar_candidatos
                    from core.storage.models import ProcessedFile

                    credentials_info = get_secret(["gcp_service_account"])
                    credentials_info = dict(credentials_info) if credentials_info else None
                    service_account_file = None if credentials_info else settings.GOOGLE_SERVICE_ACCOUNT_FILE

                    contenido = descargar_contenido(archivo["id"], credentials_info, service_account_file)
                    tipo = detectar_tipo_archivo(contenido)
                    st.write(f"Tipo detectado: **{tipo}**")

                    if tipo == "movimientos":
                        ids_existentes = {t.id_externo for t in repo.list_transactions() if t.id_externo}
                        resultado = parsear_movimientos_csv(contenido, ids_externos_existentes=ids_existentes)
                        st.write(f"{len(resultado.candidatos)} movimiento(s) nuevo(s) para importar.")
                        resumen = importar_candidatos(resultado.candidatos, repo, username, origen=f"Drive: {archivo['name']}")
                        st.success(f"Importados: {resumen.importados}")
                        if resumen.pendientes_de_ratio:
                            st.warning(f"Sin ratio (no importados): {', '.join(resumen.pendientes_de_ratio)}")
                        repo.add_processed_file(
                            ProcessedFile(
                                drive_file_id=archivo["id"], nombre_archivo=archivo["name"],
                                tipo_detectado=tipo, filas_importadas=resumen.importados,
                            )
                        )
                    elif tipo == "portfolio_report":
                        st.info(
                            "Es un reporte de cartera — andá a 📥 Importar Broker → Reconciliar Cartera "
                            "para compararlo (subilo ahí manualmente; la reconciliación no se automatiza "
                            "para que siempre la revises vos)."
                        )
                        repo.add_processed_file(
                            ProcessedFile(drive_file_id=archivo["id"], nombre_archivo=archivo["name"], tipo_detectado=tipo)
                        )
                    else:
                        st.warning("No se pudo identificar el tipo por columnas. Se marca como revisado para no volver a mostrarlo.")
                        repo.add_processed_file(
                            ProcessedFile(drive_file_id=archivo["id"], nombre_archivo=archivo["name"], tipo_detectado=tipo)
                        )
                    st.cache_data.clear()
                    st.rerun()

st.divider()
st.subheader("Snapshots históricos guardados")
st.caption("Se guardan desde el botón '📸 Guardar snapshot de hoy' en el Dashboard.")
repo = get_repository()
snapshots = repo.list_snapshots()
if not snapshots:
    st.info("Todavía no guardaste ningún snapshot.")
else:
    df_snap = pd.DataFrame([s.model_dump(exclude={"composicion_json"}) for s in snapshots])
    st.dataframe(df_snap, width="stretch", hide_index=True)

st.divider()
st.subheader("Registro de auditoría")
st.caption("Cada alta, reverso o acción sensible queda registrada acá, con usuario y timestamp.")
eventos = repo.list_audit_events(limit=100)
if not eventos:
    st.info("Todavía no hay eventos de auditoría.")
else:
    df = pd.DataFrame([e.model_dump() for e in eventos])
    st.dataframe(df, width="stretch", hide_index=True)
