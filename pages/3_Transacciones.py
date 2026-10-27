from datetime import date

import pandas as pd
import streamlit as st

from app_helpers import invalidar_caches, obtener_instrumentos, obtener_transacciones, require_login
from config.settings import settings
from core import data_providers
from core.data_providers.comafi_ratios import obtener_ratio
from core.storage import get_repository
from core.storage.models import (
    AuditEvent,
    Currency,
    Instrumento,
    TipoInstrumento,
    Transaction,
    TransactionAction,
    ids_reversados,
)
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
    with st.expander("❓ ¿Cómo cargo una compra? (leelo la primera vez)"):
        st.markdown(
            """
1. **Ticker**: el código con el que figura en tu broker (ej: `NU`, `AAPL`, `GGAL`, `YPFD`).
2. Si es la primera vez que cargás ese ticker, la app te pide **definirlo una sola vez**
   (si es acción argentina o CEDEAR, y su ratio). Después no te lo vuelve a pedir.
3. Cargá la operación: **fecha**, **cantidad** (cuántos papeles compraste o vendiste),
   **precio por unidad** y **comisión**.

**Ejemplo:** compraste 2 CEDEARs de Nubank a $ 9.500 cada uno y pagaste $ 120 de comisión →
Ticker `NU` · CEDEAR · ticker en EEUU `NU` · ratio `2` · Cantidad `2` · Precio `9500` · Comisión `120`.

¿Te equivocaste? No se edita ni se borra: más abajo está **Reversar una transacción**.
"""
        )
    ticker_input = st.text_input(
        "Ticker (como figura en tu broker)", "", placeholder="NU, AAPL, GGAL...",
        help="El código en BYMA / tu broker. Para la mayoría de los CEDEARs es el mismo que en EEUU (NU, AAPL, MELI).",
    ).upper().strip()
    instrumento_existente = instrumentos.get(ticker_input) if ticker_input else None

    if ticker_input and not instrumento_existente:
        st.warning(f"'{ticker_input}' es nuevo. Definilo una sola vez y después cargás la operación.")
        ratio_comafi = obtener_ratio(ticker_input, settings.CEDEAR_RATIOS_FILE)
        # El tipo va FUERA del form: dentro de un st.form cambiarlo no recalcula la página,
        # y el ratio de Comafi y el ADR no se autocompletaban.
        tipo_nuevo = st.radio(
            "¿Qué es?", [TipoInstrumento.ACCION_ARG.value, TipoInstrumento.CEDEAR.value],
            format_func=lambda v: "🇦🇷 Acción argentina" if v == "ACCION_ARG" else "🌎 CEDEAR",
            index=1 if ratio_comafi else 0,
            horizontal=True,
            help="Acción argentina: empresa local (GGAL, YPFD, PAMP). "
            "CEDEAR: acción de afuera que comprás en pesos en BYMA (NU, AAPL, MELI).",
        )
        es_cedear = tipo_nuevo == TipoInstrumento.CEDEAR.value
        if es_cedear:
            if ratio_comafi:
                st.caption(f"✅ Según Comafi: **{ratio_comafi:g} CEDEARs = 1 acción** de {ticker_input}. Ya quedó completado abajo.")
            else:
                st.caption(
                    f"⚠️ No encontré {ticker_input} en el listado de Comafi. Buscá el ratio en tu broker "
                    "o en comafi.com.ar (CEDEARs) y cargalo a mano."
                )
        with st.form("registrar_instrumento_inline"):
            if es_cedear:
                col1, col2 = st.columns(2)
                with col1:
                    ticker_usd_nuevo = st.text_input(
                        "Ticker en EEUU (ADR)", value=ticker_input,
                        help="Cómo cotiza la acción en Wall Street. Casi siempre es igual al de BYMA "
                        "(NU → NU). Excepción típica: BRKB → BRK-B. Se usa para traer precios en dólares.",
                    )
                with col2:
                    ratio_nuevo = st.number_input(
                        "Ratio: cuántos CEDEARs = 1 acción", min_value=0.0, step=1.0, value=float(ratio_comafi or 0),
                        help="Si el ratio es 2:1 (2 CEDEARs = 1 acción), poné 2. Solo el número de la izquierda.",
                    )
            else:
                ticker_usd_nuevo, ratio_nuevo = "", 0.0
                st.caption("Para una acción argentina no hace falta nada más: el precio sale de BYMA en pesos.")
            nombre_nuevo = st.text_input("Nombre (opcional, para reconocerlo)", "", placeholder="Nubank")
            registrar = st.form_submit_button("✅ Registrar instrumento", type="primary")

        if registrar and es_cedear and not ratio_nuevo:
            st.error("Falta el ratio del CEDEAR. Si es 2:1, poné 2.")
        elif registrar:
            try:
                inst = Instrumento(
                    ticker=ticker_input,
                    tipo_instrumento=TipoInstrumento(tipo_nuevo),
                    ticker_usd=(ticker_usd_nuevo or None) if tipo_nuevo == "CEDEAR" else None,
                    ratio_cedear=ratio_nuevo if tipo_nuevo == "CEDEAR" else None,
                    nombre=nombre_nuevo,
                )
                repo.upsert_instrumento(inst)
                repo.add_audit_event(
                    AuditEvent(usuario=username, accion="ALTA_INSTRUMENTO", detalle=f"{ticker_input}: {tipo_nuevo}")
                )
                invalidar_caches()
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

        unidad = "CEDEARs" if instrumento_existente.tipo_instrumento == TipoInstrumento.CEDEAR else "acciones"
        st.caption(
            f"**Cantidad** = cuántos {unidad} compraste o vendiste. **Precio** = lo que pagaste por "
            "cada uno, sin la comisión. **Comisión** = el total que te cobró el broker por la operación."
        )
        with st.form("nueva_transaccion", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                fecha = st.date_input("Fecha", value=date.today(), max_value=date.today())
                accion = st.selectbox("Acción", [TransactionAction.COMPRA.value, TransactionAction.VENTA.value])
            with col2:
                cantidad = st.number_input(
                    f"Cantidad de {unidad}", min_value=0.0, step=1.0, format="%.4f",
                    help=f"Ej: compraste 2 {unidad} → 2. No conviertas nada: el ratio ya lo sabe la app.",
                )
                precio = st.number_input(
                    "Precio por unidad", min_value=0.0, step=0.01, format="%.2f",
                    help="El precio de UN papel, en la moneda de al lado. Lo ves en el comprobante del broker.",
                )
            with col3:
                moneda = st.selectbox(
                    "Moneda", [Currency.ARS.value, Currency.USD.value],
                    help="ARS si pagaste en pesos (lo normal). USD si la compraste en dólares: "
                    "se pasa a pesos con el CCL de esa fecha.",
                )
                comision = st.number_input(
                    "Comisión total", min_value=0.0, step=0.01, format="%.2f", value=0.0,
                    help="Todo lo que te cobró el broker (comisión + derechos + IVA), en la misma moneda. Si no sabés, dejá 0.",
                )

            forzar = st.checkbox(
                "Forzar carga (ignorar aviso de posible duplicado)", value=False,
                help="Solo si la app te avisó que parece repetida y de verdad hiciste dos operaciones iguales.",
            )
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
                        invalidar_caches()
                        st.rerun()

    st.divider()
    st.subheader("Historial de transacciones")
    transacciones = obtener_transacciones()

    if not transacciones:
        st.info("Todavía no hay transacciones cargadas.")
    else:
        anuladas = ids_reversados(transacciones)

        def _estado(t: Transaction) -> str:
            if t.revierte_a:
                return "↩️ Reverso"
            if t.id in anuladas:
                return "❌ Anulada"
            return "✅ Vigente"

        filas = [
            {
                "Estado": _estado(t),
                "Fecha": t.fecha,
                "Operación": "🟢 Compra" if t.accion == TransactionAction.COMPRA else "🔴 Venta",
                "Ticker": t.ticker,
                "Cantidad": t.cantidad,
                "Precio": t.precio,
                "Moneda": t.moneda.value,
                "Comisión": t.comision,
                "Total": t.cantidad * t.precio + (t.comision if t.accion == TransactionAction.COMPRA else -t.comision),
                "Notas": t.notas,
                "ID": t.id,
            }
            for t in sorted(transacciones, key=lambda x: (x.fecha, x.creado_en), reverse=True)
        ]
        solo_vigentes = st.toggle("Ocultar anuladas y reversos", value=False)
        if solo_vigentes:
            filas = [f for f in filas if f["Estado"] == "✅ Vigente"]
        st.dataframe(
            pd.DataFrame(filas),
            width="stretch",
            hide_index=True,
            column_config={
                "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Cantidad": st.column_config.NumberColumn(format="%g"),
                "Precio": st.column_config.NumberColumn(format="%.2f"),
                "Comisión": st.column_config.NumberColumn(format="%.2f"),
                "Total": st.column_config.NumberColumn(
                    format="%.2f", help="Cantidad × precio, más la comisión en compras (menos en ventas). En la moneda de la fila."
                ),
                "ID": st.column_config.TextColumn(help="Identificador interno: lo vas a ver al reversar."),
            },
        )

        st.divider()
        st.subheader("Reversar una transacción")
        st.caption(
            "No se edita ni se borra: se agrega un reverso que ANULA la transacción original. Ambas quedan "
            "en el historial (marcadas), y ninguna de las dos cuenta para la cartera, el costo ni los escenarios."
        )
        reversables = [t for t in sorted(transacciones, key=lambda x: x.fecha, reverse=True) if not t.revierte_a and t.id not in anuladas]
        etiquetas = {
            t.id: f"{t.id} · {t.fecha} · {t.accion.value} {t.cantidad:g} {t.ticker} @ {t.precio:,.2f}" for t in reversables
        }
        col1, col2 = st.columns([1, 2])
        with col1:
            id_a_reversar = st.selectbox(
                "Transacción", list(etiquetas), format_func=lambda i: etiquetas[i],
                index=None, placeholder="Elegí una transacción vigente",
            )
        with col2:
            motivo = st.text_input("Motivo del reverso")
        if st.button("Reversar transacción"):
            if not id_a_reversar:
                st.error("Elegí qué transacción reversar.")
            elif not motivo:
                st.error("Indicá un motivo para el reverso (queda en el registro de auditoría).")
            else:
                try:
                    repo.add_reversal(id_a_reversar, motivo, usuario=username)
                    st.success("Reverso cargado correctamente.")
                    invalidar_caches()
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
        df_inst = pd.DataFrame(
            [
                {
                    "Ticker": i.ticker,
                    "Tipo": "🌎 CEDEAR" if i.tipo_instrumento == TipoInstrumento.CEDEAR else "🇦🇷 Acción argentina",
                    "Ticker en EEUU": i.ticker_usd or "—",
                    "Ratio": f"{i.ratio_cedear:g}:1" if i.ratio_cedear else "—",
                    "Nombre": i.nombre,
                    "Actualizado": i.actualizado_en.strftime("%d/%m/%Y"),
                }
                for i in sorted(instrumentos.values(), key=lambda x: x.ticker)
            ]
        )
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
                ratio_edit = st.number_input(
                    "Ratio: cuántos CEDEARs = 1 acción", min_value=0.0, step=1.0,
                    value=float(inst_actual.ratio_cedear or 0),
                    help="Si es 2:1, poné 2. Para una acción argentina dejá 0.",
                )
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
                invalidar_caches()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error de validación: {exc}")
