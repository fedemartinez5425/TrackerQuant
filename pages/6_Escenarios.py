from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app_helpers import (
    formato_moneda,
    formato_pct,
    obtener_historicos_riesgo,
    obtener_instrumentos,
    obtener_transacciones,
    require_login,
)
from config.settings import settings
from core import data_providers
from core.portfolio.historicos import desde_posiciones, historicos_usd_equivalente
from core.portfolio.portfolio_engine import (
    cartera_a_dataframe,
    construir_cartera,
    construir_cartera_a_fecha,
    resumen_cartera,
)
from core.risk.summary import calcular_resumen_riesgo
from core.storage.models import Currency, Instrumento, TipoInstrumento, Transaction, TransactionAction

username = require_login()

st.title("🕰️ Escenarios")
st.caption("Explorá tu cartera fuera del presente: hacia atrás (qué riesgo tenías) o hacia un supuesto (qué pasaría si).")

instrumentos = obtener_instrumentos()
tab_historico, tab_simulador = st.tabs(["🕰️ Riesgo Histórico", "🔮 Simulador"])

# ==================== TAB 1: RIESGO HISTÓRICO ====================
with tab_historico:
    st.caption(
        "Reconstruye tu cartera y su riesgo a una fecha pasada usando el log completo de "
        "transacciones + precios históricos."
    )
    transacciones = obtener_transacciones()
    if not transacciones:
        st.info("Todavía no cargaste ninguna transacción.")
    else:
        fecha_min = min(t.fecha for t in transacciones)
        fecha_corte = st.date_input(
            "Ver la cartera como estaba al...",
            value=max(fecha_min, date.today() - timedelta(days=30)),
            min_value=fecha_min,
            max_value=date.today(),
        )

        posiciones_historicas = construir_cartera_a_fecha(transacciones, fecha_corte, instrumentos)

        if not posiciones_historicas:
            st.info(f"No tenías ninguna posición abierta al {fecha_corte}.")
        else:
            resumen_h = resumen_cartera(posiciones_historicas)

            st.markdown(f"##### Composición al {fecha_corte}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Valor (con precios de HOY)", formato_moneda(resumen_h["valor_actual_total"]))
            c2.metric("Posiciones abiertas", resumen_h["cantidad_posiciones"])
            c3.metric("Tickers", ", ".join(p.ticker for p in posiciones_historicas))

            st.caption(
                "⚠️ El valor de arriba usa precios de HOY para las cantidades que tenías en esa "
                "fecha. El riesgo de abajo usa la ventana de precios históricos que TERMINA en la "
                "fecha elegida (para ver el riesgo tal como era en ese momento)."
            )

            pesos_h = {p.ticker: p.peso for p in posiciones_historicas if p.peso}
            instrumentos_h = desde_posiciones(posiciones_historicas)
            historicos_completos = historicos_usd_equivalente(instrumentos_h, period="5y")

            if historicos_completos.empty:
                st.warning("No se pudo obtener histórico de precios para reconstruir el riesgo.")
            else:
                historicos_hasta_fecha = historicos_completos.loc[: pd.Timestamp(fecha_corte)]
                if len(historicos_hasta_fecha) < 20:
                    st.warning(f"Muy pocos datos hasta el {fecha_corte} para un cálculo confiable (se necesitan ~20 días).")
                else:
                    benchmark_hist = data_providers.get_history(settings.DEFAULT_BENCHMARK, period="5y")
                    if benchmark_hist is not None and not benchmark_hist.empty:
                        benchmark_hasta_fecha = benchmark_hist.loc[: pd.Timestamp(fecha_corte)]
                        historicos_hasta_fecha = pd.concat(
                            [historicos_hasta_fecha, benchmark_hasta_fecha], axis=1
                        ).ffill().dropna(how="all")

                    riesgo_h = calcular_resumen_riesgo(
                        historicos_hasta_fecha, pesos_h, resumen_h["valor_actual_total"],
                        settings.DEFAULT_BENCHMARK, settings.STRESS_SCENARIOS,
                    )

                    st.markdown(f"##### Riesgo tal como era al {fecha_corte}")
                    d1, d2, d3, d4 = st.columns(4)
                    d1.metric("Semáforo", riesgo_h["semaforo"])
                    d2.metric("Volatilidad Anual.", formato_pct(riesgo_h["volatilidad_anualizada"]))
                    d3.metric("VaR histórico 95%", formato_pct(riesgo_h["var_95_pct"]))
                    d4.metric(f"Beta vs. {settings.DEFAULT_BENCHMARK}", f"{riesgo_h['beta_cartera']:.2f}" if riesgo_h["beta_cartera"] else "—")
                    st.caption(f"Calculado con datos hasta el {fecha_corte} — sin ver nada posterior a esa fecha.")

# ==================== TAB 2: SIMULADOR ====================
with tab_simulador:
    st.caption(
        "⚠️ Esto NO predice precios futuros — es un ejercicio de 'qué pasaría si': agregás compras "
        "hipotéticas (a precios de HOY) y ves cómo cambiaría tu cartera. Nada de esto se guarda."
    )

    @dataclass
    class CompraHipotetica:
        ticker: str
        tipo_instrumento: TipoInstrumento
        ticker_usd: str | None
        ratio_cedear: float | None
        cantidad: float
        precio: float

    transacciones_reales = obtener_transacciones()
    if "compras_hipoteticas" not in st.session_state:
        st.session_state["compras_hipoteticas"] = []

    with st.form("compra_hipotetica", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            tipo_ui = st.radio(
                "Tipo", [TipoInstrumento.ACCION_ARG.value, TipoInstrumento.CEDEAR.value],
                format_func=lambda v: "🇦🇷 Acción ARG" if v == "ACCION_ARG" else "🌎 CEDEAR",
                horizontal=True,
            )
            ticker_sim = st.text_input("Ticker BCBA", "").upper().strip()
        with col2:
            cantidad_sim = st.number_input("Cantidad a agregar", min_value=0.0, step=1.0)
            precio_sim = st.number_input("Precio estimado ($ ARS)", min_value=0.0, step=0.01)
        with col3:
            ticker_usd_sim = st.text_input("Ticker ADR (solo CEDEAR)", "").upper().strip() if tipo_ui == "CEDEAR" else ""
            ratio_sim = st.number_input("Ratio (solo CEDEAR)", min_value=0.0, step=1.0) if tipo_ui == "CEDEAR" else None

        # Si el ticker ya existe en tu cartera real, reusa su tipo/ratio automáticamente
        if ticker_sim and ticker_sim in instrumentos:
            st.caption(f"ℹ️ '{ticker_sim}' ya está en tu cartera real — se usará su tipo/ratio registrado.")
        agregar = st.form_submit_button("➕ Agregar al escenario", type="primary")

    if agregar and ticker_sim and cantidad_sim > 0 and precio_sim > 0:
        inst_real = instrumentos.get(ticker_sim)
        try:
            nueva_hipotetica = CompraHipotetica(
                ticker=ticker_sim,
                tipo_instrumento=inst_real.tipo_instrumento if inst_real else TipoInstrumento(tipo_ui),
                ticker_usd=inst_real.ticker_usd if inst_real else ((ticker_usd_sim or None) if tipo_ui == "CEDEAR" else None),
                ratio_cedear=inst_real.ratio_cedear if inst_real else (ratio_sim if tipo_ui == "CEDEAR" else None),
                cantidad=cantidad_sim,
                precio=precio_sim,
            )
            st.session_state["compras_hipoteticas"].append(nueva_hipotetica)
            st.success(f"Agregado al escenario: +{cantidad_sim} {ticker_sim}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"No se pudo agregar: {exc}")

    if st.session_state["compras_hipoteticas"]:
        st.write("**Compras hipotéticas en este escenario:**")
        for i, t in enumerate(st.session_state["compras_hipoteticas"]):
            c1, c2 = st.columns([5, 1])
            c1.write(f"+{t.cantidad} {t.ticker} @ ${t.precio:,.2f} ({t.tipo_instrumento.value})")
            if c2.button("Quitar", key=f"quitar_{i}"):
                st.session_state["compras_hipoteticas"].pop(i)
                st.rerun()
        if st.button("🗑️ Limpiar todo el escenario"):
            st.session_state["compras_hipoteticas"] = []
            st.rerun()

    st.divider()

    if not st.session_state["compras_hipoteticas"]:
        st.info("Agregá al menos una compra hipotética para ver el escenario simulado.")
    else:
        # Instrumentos "hipotéticos" (en memoria, nunca se guardan) + transacciones hipotéticas
        instrumentos_simulados = dict(instrumentos)
        transacciones_hipoteticas = []
        for h in st.session_state["compras_hipoteticas"]:
            if h.ticker not in instrumentos_simulados:
                instrumentos_simulados[h.ticker] = Instrumento(
                    ticker=h.ticker, tipo_instrumento=h.tipo_instrumento,
                    ticker_usd=h.ticker_usd, ratio_cedear=h.ratio_cedear,
                )
            transacciones_hipoteticas.append(
                Transaction(
                    fecha=date.today(), ticker=h.ticker, accion=TransactionAction.COMPRA,
                    cantidad=h.cantidad, precio=h.precio, moneda=Currency.ARS,
                    notas="[SIMULACIÓN - no persistida]",
                )
            )

        transacciones_simuladas = transacciones_reales + transacciones_hipoteticas
        posiciones_actuales = construir_cartera(transacciones_reales, instrumentos)
        posiciones_simuladas = construir_cartera(transacciones_simuladas, instrumentos_simulados)

        resumen_actual = resumen_cartera(posiciones_actuales)
        resumen_simulado = resumen_cartera(posiciones_simuladas)

        st.markdown("##### Comparación: Cartera Actual vs. Escenario Simulado")
        col1, col2 = st.columns(2)
        col1.metric("Valor Actual (real)", formato_moneda(resumen_actual["valor_actual_total"]))
        col2.metric(
            "Valor en el Escenario", formato_moneda(resumen_simulado["valor_actual_total"]),
            delta=formato_moneda(resumen_simulado["valor_actual_total"] - resumen_actual["valor_actual_total"]),
        )

        st.dataframe(cartera_a_dataframe(posiciones_simuladas), width="stretch", hide_index=True)

        st.divider()
        st.markdown("##### Riesgo: Actual vs. Escenario")
        pesos_actual = {p.ticker: p.peso for p in posiciones_actuales if p.peso}
        pesos_simulado = {p.ticker: p.peso for p in posiciones_simuladas if p.peso}
        historicos_simulado = obtener_historicos_riesgo(posiciones_simuladas)

        if historicos_simulado.empty:
            st.warning("No se pudo obtener histórico de precios para calcular el riesgo del escenario.")
        else:
            riesgo_actual = calcular_resumen_riesgo(
                historicos_simulado, pesos_actual, resumen_actual["valor_actual_total"],
                settings.DEFAULT_BENCHMARK, settings.STRESS_SCENARIOS,
            )
            riesgo_simulado = calcular_resumen_riesgo(
                historicos_simulado, pesos_simulado, resumen_simulado["valor_actual_total"],
                settings.DEFAULT_BENCHMARK, settings.STRESS_SCENARIOS,
            )
            tabla = pd.DataFrame(
                {
                    "Métrica": ["Volatilidad Anualizada", "VaR histórico 95%", f"Beta vs. {settings.DEFAULT_BENCHMARK}", "Correlación promedio"],
                    "Actual": [
                        formato_pct(riesgo_actual["volatilidad_anualizada"]), formato_pct(riesgo_actual["var_95_pct"]),
                        f"{riesgo_actual['beta_cartera']:.2f}" if riesgo_actual["beta_cartera"] else "—",
                        f"{riesgo_actual['correlacion_ponderada']:.2f}" if riesgo_actual["correlacion_ponderada"] is not None else "—",
                    ],
                    "Escenario": [
                        formato_pct(riesgo_simulado["volatilidad_anualizada"]), formato_pct(riesgo_simulado["var_95_pct"]),
                        f"{riesgo_simulado['beta_cartera']:.2f}" if riesgo_simulado["beta_cartera"] else "—",
                        f"{riesgo_simulado['correlacion_ponderada']:.2f}" if riesgo_simulado["correlacion_ponderada"] is not None else "—",
                    ],
                }
            )
            st.dataframe(tabla, width="stretch", hide_index=True)
            st.caption("Ambas columnas usan la misma ventana de precios históricos — la diferencia viene solo de los pesos, no de precios futuros.")
