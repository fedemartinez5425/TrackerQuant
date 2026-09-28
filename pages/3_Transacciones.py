from datetime import date

import pandas as pd
import streamlit as st

from app_helpers import obtener_instrumentos, obtener_transacciones, require_login
from config.settings import settings
from core import data_providers
from core.data_providers.comafi_ratios import obtener_ratio
from core.storage import get_repository
from core.storage.models import AuditEvent, Currency, Instrumento, TipoInstrumento, Transaction, TransactionAction
from core.validation.schemas import validar_transaccion_completa

username = require_login()

st.title("📝 Transacciones")
st.caption(
    "Registro append-only: nunca se edita ni se borra una transacción, se reversa. "
    "El tipo/ratio de cada ticker se define UNA vez en 'Instrumentos' y se reusa siempre."
)

repo = get_repository()
instrumentos = obtener_instrumentos()

tab_movimiento, tab_instrumentos = st.tabs(["📝 Nueva Transacción", "🏷️ Instrumentos"])

# ==================== TAB 1: NUEVA TRANSACCIÓN ====================
with tab_movimiento:
    ticker_input = st.text_input("Ticker (BCBA)", "").upper().strip()
    instrumento_existente = instrumentos.get(ticker_input) if ticker_input else None

    if ticker_input and not instrumento_existente:
        st.warning(f"'{ticker_input}' todavía no está registrado en Instrumentos. Definilo primero (una sola vez):")
        with st.form("registrar_instrumento_inline"):
            col1, col2 = st.columns(2)
            with col1:
                tipo_nuevo = st.radio(
                    "Tipo", [TipoInstrumento.ACCION_ARG.value, TipoInstrumento.CEDEAR.value],
                    format_func=lambda v: "🇦🇷 Acción Argentina" if v == "ACCION_ARG" else "🌎 CEDEAR",
                    horizontal=True,
                )
            with col2:
                ratio_sugerido = obtener_ratio(ticker_input, settings.CEDEAR_RATIOS_FILE) if tipo_nuevo == "CEDEAR" else None
                ticker_usd_nuevo = st.text_input("Ticker ADR (EEUU)", value=ticker_input if tipo_nuevo == "CEDEAR" else "")
                ratio_nuevo = st.number_input(
                    "Ratio CEDEAR (X:1)", min_value=0.0, step=1.0, value=float(ratio_sugerido or 0)
                )
            nombre_nuevo = st.text_input("Nombre descriptivo (opcional)", "")
            registrar = st.form_submit_button("✅ Registrar instrumento", type="primary")

        if registrar:
            try:
                inst = Instrumento(
                    ticker=ticker_input,
                    tipo_instrumento=TipoInstrumento(tipo_nuevo),
                    ticker_usd=(ticker_usd_nuevo or None) if tipo_nuevo == "CEDEAR" else None,
                    ratio_cedear=ratio_nuevo if tipo_nuevo == "CEDEAR" else None,
                    nombre=nombre_nuevo,
                )
                repo.upsert_instrumento(inst)
                st.success(f"Instrumento {ticker_input} registrado. Ahora cargá la transacción abajo.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error de validación: {exc}")

    elif instrumento_existente:
        st.info(
            f"**{ticker_input}** ya registrado como "
            f"{'🌎 CEDEAR' if instrumento_existente.tipo_instrumento == TipoInstrumento.CEDEAR else '🇦🇷 Acción Argentina'}"
            + (f" (ADR: {instrumento_existente.ticker_usd}, ratio {instrumento_existente.ratio_cedear:g}:1)" if instrumento_existente.ticker_usd else "")
        )

        with st.form("nueva_transaccion", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                fecha = st.date_input("Fecha", value=date.today(), max_value=date.today())
                accion = st.selectbox("Acción", [TransactionAction.COMPRA.value, TransactionAction.VENTA.value])
            with col2:
                cantidad = st.number_input("Cantidad", min_value=0.0, step=1.0, format="%.4f")
                precio = st.number_input("Precio (en BCBA, $ ARS)", min_value=0.0, step=0.01, format="%.2f")
            with col3:
                moneda = st.selectbox("Moneda", [Currency.ARS.value, Currency.USD.value])
                comision = st.number_input("Comisión", min_value=0.0, step=0.01, format="%.2f", value=0.0)

            forzar = st.checkbox("Forzar carga (ignorar aviso de posible duplicado)", value=False)
            notas = st.text_area("Notas (opcional)", "")
            enviado = st.form_submit_button("Validar y cargar transacción", type="primary")

        if enviado:
            errores_previos = []
            if cantidad <= 0:
                errores_previos.append("La cantidad debe ser mayor a 0.")
            if precio <= 0:
                errores_previos.append("El precio debe ser mayor a 0.")

            if errores_previos:
                for e in errores_previos:
                    st.error(e)
            else:
                try:
                    nueva = Transaction(
                        fecha=fecha, ticker=ticker_input, accion=TransactionAction(accion),
                        cantidad=cantidad, precio=precio, moneda=Currency(moneda),
                        comision=comision, notas=notas,
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Error de validación: {exc}")
                else:
                    existentes = obtener_transacciones()
                    ticker_a_validar = (
                        instrumento_existente.ticker_usd
                        if instrumento_existente.tipo_instrumento == TipoInstrumento.CEDEAR
                        else f"{ticker_input}.BA"
                    )
                    resultado = validar_transaccion_completa(
                        nueva, existentes, provider=data_providers, forzar=forzar, ticker_a_validar=ticker_a_validar
                    )
                    if not resultado.ok:
                        st.error("No se pudo cargar la transacción:")
                        for e in resultado.errores:
                            st.write(f"- {e}")
                    else:
                        repo.add_transaction(nueva)
                        repo.add_audit_event(
                            AuditEvent(
                                usuario=username, accion="ALTA_TRANSACCION",
                                detalle=f"{nueva.accion.value} {nueva.cantidad} {nueva.ticker} @ {nueva.precio}",
                            )
                        )
                        st.success(f"Transacción cargada: {nueva.accion.value} {nueva.cantidad} {nueva.ticker} @ {nueva.precio}")
                        st.cache_data.clear()
                        st.rerun()

    st.divider()
    st.subheader("Historial de transacciones")
    transacciones = obtener_transacciones()

    if not transacciones:
        st.info("Todavía no hay transacciones cargadas.")
    else:
        df = pd.DataFrame([t.to_row() for t in sorted(transacciones, key=lambda x: x.fecha, reverse=True)])
        st.dataframe(df, width="stretch", hide_index=True)

        st.divider()
        st.subheader("Reversar una transacción")
        st.caption("No se edita ni se borra: se agrega el movimiento inverso, dejando ambos en el historial.")
        ids_disponibles = [t.id for t in transacciones]
        col1, col2 = st.columns([1, 2])
        with col1:
            id_a_reversar = st.selectbox("ID de transacción", ids_disponibles)
        with col2:
            motivo = st.text_input("Motivo del reverso")
        if st.button("Reversar transacción"):
            if not motivo:
                st.error("Indicá un motivo para el reverso (queda en el registro de auditoría).")
            else:
                try:
                    repo.add_reversal(id_a_reversar, motivo, usuario=username)
                    st.success("Reverso cargado correctamente.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"No se pudo reversar: {exc}")

# ==================== TAB 2: INSTRUMENTOS (tabla dimensión) ====================
with tab_instrumentos:
    st.caption(
        "Tabla dimensión: cada ticker se define UNA vez acá (tipo, ADR, ratio). Todas tus "
        "transacciones de ese ticker reusan esta definición. Si un ratio cambia (split, "
        "ampliación de capital), corregilo acá y se aplica a toda la cartera."
    )
    if not instrumentos:
        st.info("Todavía no hay instrumentos registrados — se registran desde la pestaña de Nueva Transacción.")
    else:
        df_inst = pd.DataFrame([i.model_dump() for i in instrumentos.values()])
        st.dataframe(df_inst, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Editar / corregir un instrumento existente")
    if instrumentos:
        ticker_editar = st.selectbox("Ticker a editar", sorted(instrumentos.keys()))
        inst_actual = instrumentos[ticker_editar]
        with st.form("editar_instrumento"):
            col1, col2 = st.columns(2)
            with col1:
                tipo_edit = st.radio(
                    "Tipo", [TipoInstrumento.ACCION_ARG.value, TipoInstrumento.CEDEAR.value],
                    index=0 if inst_actual.tipo_instrumento == TipoInstrumento.ACCION_ARG else 1,
                    horizontal=True,
                )
            with col2:
                ticker_usd_edit = st.text_input("Ticker ADR", value=inst_actual.ticker_usd or "")
                ratio_edit = st.number_input("Ratio CEDEAR", min_value=0.0, step=1.0, value=float(inst_actual.ratio_cedear or 0))
            guardar = st.form_submit_button("💾 Guardar cambios", type="primary")

        if guardar:
            try:
                nuevo = Instrumento(
                    ticker=ticker_editar, tipo_instrumento=TipoInstrumento(tipo_edit),
                    ticker_usd=(ticker_usd_edit or None) if tipo_edit == "CEDEAR" else None,
                    ratio_cedear=ratio_edit if tipo_edit == "CEDEAR" else None,
                    nombre=inst_actual.nombre,
                )
                repo.upsert_instrumento(nuevo)
                repo.add_audit_event(
                    AuditEvent(usuario=username, accion="EDITAR_INSTRUMENTO", detalle=f"{ticker_editar}: {tipo_edit}, ratio={ratio_edit}")
                )
                st.success(f"{ticker_editar} actualizado.")
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error de validación: {exc}")
