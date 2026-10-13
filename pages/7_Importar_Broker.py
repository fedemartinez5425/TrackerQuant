import pandas as pd
import streamlit as st

from app_helpers import invalidar_caches, obtener_cartera_actual, obtener_instrumentos, obtener_transacciones, require_login
from core.importers.broker_movimientos import parsear_movimientos_csv
from core.importers.import_service import importar_candidatos
from core.importers.portfolio_report import parsear_portfolio_report_csv, reconciliar
from core.storage import get_repository

username = require_login()

st.title("📥 Importar desde el Broker")
st.caption(
    "Subí los CSV que exporta tu broker para automatizar la carga de transacciones y "
    "verificar que tu log coincida con lo que el broker dice que tenés. Para automatizar esto "
    "todavía más (sin subir el archivo a mano cada vez), ver ⚙️ Configuración → Sincronización con Drive."
)

tab_movimientos, tab_reconciliacion = st.tabs(["📝 Importar Movimientos", "🔍 Reconciliar Cartera"])

# ==================== TAB 1: IMPORTAR MOVIMIENTOS ====================
with tab_movimientos:
    st.markdown(
        "Subí el CSV de **movimientos de cuenta** (columnas `nroTicket;...;instrumento;...;cantidad;precio;...`). "
        "Se detecta automáticamente CEDEAR vs. Acción Argentina, registra el instrumento la primera vez que "
        "aparece, y **nunca se duplica** un movimiento ya importado (usa el número de ticket del broker)."
    )
    archivo_mov = st.file_uploader("CSV de movimientos", type=["csv"], key="uploader_movimientos")

    # El resultado de la última importación se guarda en sesión: antes el
    # st.rerun() posterior borraba el mensaje antes de que se pudiera leer.
    ultimo = st.session_state.pop("resultado_importacion", None)
    if ultimo:
        st.success(f"Se importaron {ultimo['importados']} movimientos correctamente.")
        if ultimo["pendientes_de_ratio"]:
            st.warning(
                f"Sin ratio, no importados: {', '.join(ultimo['pendientes_de_ratio'])}. "
                "Completá el ratio en la tabla y volvé a confirmar (los ya importados no se duplican)."
            )
        for e in ultimo["errores"]:
            st.error(e)

    if archivo_mov is not None:
        transacciones_existentes = obtener_transacciones()
        instrumentos_existentes = obtener_instrumentos()
        ids_existentes = {t.id_externo for t in transacciones_existentes if t.id_externo}

        contenido = archivo_mov.read().decode("utf-8", errors="replace")
        resultado = parsear_movimientos_csv(contenido, ids_externos_existentes=ids_existentes)

        col1, col2, col3 = st.columns(3)
        col1.metric("Movimientos nuevos a importar", len(resultado.candidatos))
        col2.metric("Ya importados (omitidos)", len(resultado.ya_importados))
        col3.metric("No aplicables (FCI, efectivo, etc.)", len(resultado.omitidos))

        if resultado.omitidos:
            with st.expander(f"Ver detalle de {len(resultado.omitidos)} filas no aplicables"):
                st.dataframe(pd.DataFrame(resultado.omitidos), width="stretch", hide_index=True)

        if not resultado.candidatos:
            st.info("No hay movimientos nuevos para importar en este archivo.")
        else:
            # Si el ticker ya está registrado en Instrumentos, se usa SU ratio
            for c in resultado.candidatos:
                existente = instrumentos_existentes.get(c.ticker)
                if existente and existente.ratio_cedear:
                    c.ratio_cedear = existente.ratio_cedear
            faltan_ratio = [c for c in resultado.candidatos if c.tipo_instrumento.value == "CEDEAR" and not c.ratio_cedear]
            if faltan_ratio:
                st.warning(
                    f"⚠️ {len(faltan_ratio)} movimiento(s) de CEDEAR no tienen ratio en el cache de Comafi. "
                    "Completalos en la columna 'Ratio CEDEAR' de la tabla antes de importar."
                )

            st.subheader("Vista previa (editable)")
            df_preview = pd.DataFrame(
                [
                    {
                        "Incluir": True, "Fecha": c.fecha, "Ticker": c.ticker, "Tipo": c.tipo_instrumento.value,
                        "Acción": c.accion.value, "Cantidad": c.cantidad, "Precio": c.precio, "Moneda": c.moneda,
                        "Ratio CEDEAR": c.ratio_cedear, "Comisión": c.comision, "ID Externo": c.id_externo,
                    }
                    for c in resultado.candidatos
                ]
            )
            df_editado = st.data_editor(
                df_preview, width="stretch", hide_index=True,
                disabled=["Fecha", "Ticker", "Tipo", "Acción", "Cantidad", "Precio", "Moneda", "Comisión", "ID Externo"],
                column_config={
                    "Incluir": st.column_config.CheckboxColumn(help="Desmarcá para no importar esta fila"),
                    "Ratio CEDEAR": st.column_config.NumberColumn(help="Completá si quedó vacío"),
                },
                key="editor_movimientos",
            )

            if st.button("✅ Confirmar e importar", type="primary"):
                repo = get_repository()
                candidatos_incluidos = [
                    resultado.candidatos[idx] for idx, fila in df_editado.iterrows() if fila["Incluir"]
                ]
                ratios_override = {
                    fila["Ticker"]: fila["Ratio CEDEAR"]
                    for _, fila in df_editado.iterrows()
                    if fila["Incluir"] and pd.notna(fila["Ratio CEDEAR"])
                }
                resumen = importar_candidatos(candidatos_incluidos, repo, username, ratios_override, origen="broker (manual)")

                st.session_state["resultado_importacion"] = {
                    "importados": resumen.importados,
                    "pendientes_de_ratio": resumen.pendientes_de_ratio,
                    "errores": resumen.errores,
                }
                invalidar_caches()
                st.rerun()

# ==================== TAB 2: RECONCILIACIÓN ====================
with tab_reconciliacion:
    st.markdown(
        "Subí el **reporte de cartera** del broker (columnas `instrumento;cantidad;precio;moneda;total`) "
        "para comparar contra lo que esta app calculó a partir de tu log de transacciones. Las diferencias "
        "suelen indicar movimientos que todavía no cargaste."
    )
    archivo_report = st.file_uploader("CSV de portfolio report", type=["csv"], key="uploader_report")

    if archivo_report is not None:
        contenido_report = archivo_report.read().decode("utf-8", errors="replace")
        resultado_report = parsear_portfolio_report_csv(contenido_report)
        posiciones_app = obtener_cartera_actual()

        filas = reconciliar(resultado_report.posiciones, posiciones_app)
        df_reconciliacion = pd.DataFrame(filas)

        hay_diferencias = any(f["Coincide"] == "⚠️" for f in filas)
        if hay_diferencias:
            st.warning("⚠️ Hay diferencias entre tu log de transacciones y lo que reporta el broker.")
        else:
            st.success("✅ Tu log de transacciones coincide exactamente con el reporte del broker.")

        st.dataframe(df_reconciliacion, width="stretch", hide_index=True)

        if resultado_report.saldo_efectivo:
            st.caption(
                "Saldo de efectivo en el broker (no trackeado como posición): "
                + ", ".join(f"{moneda} {monto:,.2f}" for moneda, monto in resultado_report.saldo_efectivo.items())
            )
