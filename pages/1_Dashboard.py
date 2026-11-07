"""
Dashboard: lo importante en 10 segundos. Arriba las alertas y los números
que deciden (plata y riesgo en pesos), después el impacto de la última
operación y abajo los gráficos con el dato relevante ya escrito en el título.
"""
import streamlit as st

from app_helpers import (
    avisar_excluidos,
    formato_moneda,
    mostrar_ccl_sidebar,
    mostrar_frescura,
    obtener_cartera_actual,
    obtener_historicos_riesgo,
    obtener_impacto_ultima_operacion,
    require_login,
    tarjeta_alerta,
)
from config.settings import settings
from core.decision.ultima_operacion import lectura_impacto
from core.insights.rules_engine import generar_insights
from core.portfolio.portfolio_engine import resumen_cartera
from core.portfolio.snapshot import armar_snapshot
from core.risk.summary import calcular_resumen_riesgo
from core.storage import get_repository
from core.viz import charts, formato
from core.viz import palette as p
from core.viz import semaforos

require_login()
mostrar_ccl_sidebar()

st.title("📊 Dashboard")
mostrar_frescura()

posiciones = obtener_cartera_actual()
if not posiciones:
    st.info("Todavía no cargaste ninguna transacción: cargá tu primera compra y el tablero se arma solo.")
    c1, c2 = st.columns(2)
    c1.page_link("pages/3_Transacciones.py", label="Cargar una compra a mano", icon="📝")
    c2.page_link("pages/7_Importar_Broker.py", label="Importar el CSV del broker", icon="📥")
    st.stop()

resumen = resumen_cartera(posiciones)
pesos = {p_.ticker: p_.peso for p_ in posiciones if p_.peso}
historicos = obtener_historicos_riesgo(posiciones)

if historicos.empty:
    st.warning(
        "No se pudo obtener histórico de precios en este momento para calcular el riesgo. "
        "Mirá **Estado del sistema** para ver si Yahoo o el almacén están caídos."
    )
    st.page_link("pages/12_Estado.py", label="Ir a Estado del sistema", icon="🩺")
    st.stop()

riesgo = calcular_resumen_riesgo(
    historicos, pesos, resumen["valor_actual_total"], settings.DEFAULT_BENCHMARK, settings.STRESS_SCENARIOS
)
avisar_excluidos(historicos)

# ==================== Alertas arriba: lo que pide atención ====================
color_semaforo = p.color_semaforo(riesgo["semaforo"])
st.markdown(
    f"""
    <div role="status" style="background:{color_semaforo}18; border:1px solid {color_semaforo}55;
    border-radius:12px; padding:0.75rem 1.1rem; margin:0.4rem 0 0.8rem 0; display:flex; flex-wrap:wrap;
    gap:0.4rem 1rem; justify-content:space-between; align-items:center;">
        <div>
            <span style="font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.1rem;
            color:{color_semaforo};">Riesgo de la cartera: {riesgo['semaforo']}</span>
            <span style="color:{p.TEXT_SECONDARY}; font-size:0.85rem; margin-left:8px;">
            según volatilidad anual y concentración en las 2 posiciones más grandes</span>
        </div>
        <div style="font-family:'JetBrains Mono',monospace; color:{p.TEXT_SECONDARY}; font-size:0.85rem;">
        {resumen['cantidad_posiciones']} posiciones</div>
    </div>
    """,
    unsafe_allow_html=True,
)

insights = generar_insights(riesgo, posiciones, settings.DEFAULT_BENCHMARK)
alertas = [i for i in insights if i.severidad in ("alto", "medio")]
for i in alertas[:3]:
    tarjeta_alerta(i.severidad, i.diagnostico, i.categoria)
if len(alertas) > 3:
    st.caption(f"…y {len(alertas) - 3} señal(es) más en el reporte.")
if not alertas:
    tarjeta_alerta("bajo", "Sin señales de alerta relevantes en este momento.")

# ==================== KPIs: plata arriba, riesgo abajo ====================
var_pesos = abs(riesgo["var_95_usd"]) if riesgo["var_95_usd"] is not None else None
cvar_pesos = abs(riesgo["cvar_95_usd"]) if riesgo["cvar_95_usd"] is not None else None
mayor = max(posiciones, key=lambda p_: p_.peso or 0)

k1, k2, k3 = st.columns(3)
k1.metric(
    "Valor de la cartera", formato_moneda(resumen["valor_actual_total"]),
    delta=f"{formato.pct(resumen['ganancia_perdida_pct_total'], 1, signo=True)} en pesos"
    if resumen["ganancia_perdida_pct_total"] is not None else None,
    help=f"G/P en pesos: {formato_moneda(resumen['ganancia_perdida_total'])} sobre lo invertido.",
)
k2.metric(
    "G/P en dólares (CCL)",
    formato_moneda(resumen["ganancia_perdida_usd_total"], "USD"),
    delta=formato.pct(resumen["ganancia_perdida_usd_pct_total"], 1, signo=True)
    if resumen["ganancia_perdida_usd_pct_total"] is not None else None,
    help="Cada compra al CCL de su fecha contra el valor de hoy al CCL de hoy: si ganás en pesos pero "
    "perdés acá, la suba fue solo por el dólar.",
)
k3.metric(
    "Pérdida en un mal día", formato_moneda(var_pesos),
    delta=f"{formato.pct(abs(riesgo['var_95_pct']), 2)} de la cartera" if riesgo["var_95_pct"] is not None else None,
    delta_color="off", delta_arrow="off",
    help="VaR 95 % a 1 día: en 1 de cada 20 días la pérdida fue MAYOR a este monto (histórico, pesos de hoy).",
)

vol = riesgo["volatilidad_anualizada"]
k4, k5, k6 = st.columns(3)
k4.metric(
    "Volatilidad anual",
    f"{semaforos.senal([semaforos.nivel(vol, 'volatilidad')])} {formato.pct(vol, 1)}" if vol is not None else "—",
    help=f"Cuánto se mueve la cartera en un año típico. 🟢 ≤ {formato.pct(semaforos.VOL_MEDIA, 0)} · "
    f"🟡 hasta {formato.pct(semaforos.VOL_ALTA, 0)} · 🔴 más.",
)
k5.metric(
    "Pérdida en los peores días", formato_moneda(cvar_pesos),
    delta=f"{formato.pct(abs(riesgo['cvar_95_pct']), 2)} de la cartera" if riesgo["cvar_95_pct"] is not None else None,
    delta_color="off", delta_arrow="off",
    help="Expected Shortfall 95 %: cuando toca uno de los peores 5 % de días, esto se pierde en promedio.",
)
nivel_mayor = semaforos.nivel(mayor.peso, "peso")
k6.metric(
    "Posición más grande",
    f"{semaforos.senal([nivel_mayor])} {mayor.ticker} · {formato.pct(mayor.peso, 1)}",
    help=f"🟡 más de {formato.pct(semaforos.PESO_MEDIO, 0)} · 🔴 más de {formato.pct(semaforos.PESO_ALTO, 0)} de la cartera.",
)

# ==================== Impacto de la última operación ====================
st.divider()
impacto = obtener_impacto_ultima_operacion(posiciones)
if impacto:
    operacion, filas = impacto
    simbolo = "US$" if operacion.moneda.value == "USD" else "$"
    st.markdown(
        f"##### 🧾 Tu última operación: {operacion.accion.value.lower()} de {formato.fmt(operacion.cantidad, 'g')} "
        f"{operacion.ticker} el {operacion.fecha:%d/%m/%Y} a {simbolo} {formato.fmt(operacion.precio, ',.2f')}"
    )
    if not filas or all(f.antes is None for f in filas):
        st.caption("Es tu primera operación (o no hay historia para comparar): no hay un 'antes' contra qué medir.")
    else:
        for severidad, texto in lectura_impacto(filas, operacion.ticker, semaforos.PESO_ALTO, semaforos.PESO_MEDIO):
            tarjeta_alerta(severidad, texto)
        destacadas = {f.metrica: f for f in filas}
        cols = st.columns(4)
        # Métrica completa -> etiqueta corta para la tarjeta (el nombre largo va en la tabla).
        claves = {
            f"Peso de {operacion.ticker}": f"Peso de {operacion.ticker}",
            "Volatilidad anual": "Volatilidad anual",
            "Pérdida en un mal día (VaR 95%)": "Mal día (VaR 95 %)",
            f"Aporte de {operacion.ticker} al riesgo": "Aporte al riesgo",
        }

        def _valor(f, v):
            if v is None:
                return "—"
            return formato_moneda(v) if f.formato == "moneda" else formato.pct(v, 1) if f.formato == "pct" else formato.fmt(v, ".2f")

        for col, (clave, etiqueta) in zip(cols, claves.items()):
            f = destacadas.get(clave)
            if not f:
                continue
            delta = None
            if f.delta is not None:
                delta = (
                    formato_moneda(f.delta) if f.formato == "moneda" else
                    f"{formato.fmt(f.delta * 100, '+.1f')} pp" if f.formato == "pct" else formato.fmt(f.delta, "+.2f")
                )
            col.metric(
                etiqueta, _valor(f, f.despues), delta=delta,
                # Si subir es malo, una suba se pinta en rojo.
                delta_color="inverse" if f.sube_es_malo else "off" if f.sube_es_malo is None else "normal",
                help=f"{f.ayuda} Antes de la operación: {_valor(f, f.antes)}.",
            )
        with st.expander("Ver todas las métricas antes / después"):
            st.dataframe(
                [
                    {
                        "Métrica": f.metrica,
                        "Antes": _valor(f, f.antes),
                        "Después": _valor(f, f.despues),
                        "Cambio": ("🔴 empeora" if f.empeora else "🟢 mejora" if (f.delta and f.sube_es_malo is not None) else "—"),
                    }
                    for f in filas
                ],
                hide_index=True, width="stretch",
            )
            st.caption(
                "Antes = la cartera sin esta operación; después = la de hoy. Las dos a precios de hoy y sobre "
                "la misma historia: la diferencia es solo por la operación. Es un backtest, no una predicción."
            )

# ==================== Gráficos: el dato en el título ====================
st.divider()
col_izq, col_der = st.columns([1.6, 1])
with col_izq:
    indice = riesgo["indice_cartera"]
    if not indice.empty:
        caida = indice.iloc[-1] / indice.max() - 1
        titulo = (
            f"Evolución (base 100): hoy {formato.fmt(indice.iloc[-1], '.1f')}"
            + (f", {formato.pct(caida, 1)} desde el máximo" if caida < -0.005 else ", en máximos")
        )
        st.markdown(f"##### {titulo}")
        st.caption("Con los pesos de HOY aplicados a toda la historia (no es tu rendimiento real).")
        st.plotly_chart(charts.area_evolucion(indice), width="stretch")
        st.page_link("pages/13_Evolucion.py", label="Ver tu evolución real (con tus compras y ventas)", icon="📆")
    else:
        st.info("Sin datos suficientes para graficar la evolución.")

with col_der:
    sobre_umbral = [t for t, w in pesos.items() if w > semaforos.PESO_ALTO]
    st.markdown(
        f"##### Exposición: {mayor.ticker} es el {formato.pct(mayor.peso, 0)}"
        + (f" · 🔴 {len(sobre_umbral)} posición(es) > {formato.pct(semaforos.PESO_ALTO, 0)}" if sobre_umbral else "")
    )
    st.plotly_chart(charts.donut_exposicion(pesos, umbral_alerta=semaforos.PESO_ALTO), width="stretch")

col_izq2, col_der2 = st.columns([1, 1])
with col_izq2:
    retornos = riesgo["retorno_cartera"]
    if not retornos.empty:
        dias_negativos = (retornos < 0).mean()
        st.markdown(f"##### Retornos diarios: {formato.pct(dias_negativos, 0)} de los días fueron negativos")
        st.plotly_chart(charts.histograma_retornos(retornos, var_pct=riesgo["var_95_pct"]), width="stretch")
        if riesgo["peor_dia_pct"] is not None:
            fecha = riesgo["peor_dia_fecha"]
            fecha_str = fecha.strftime("%d/%m/%Y") if hasattr(fecha, "strftime") else fecha
            st.caption(f"En rojo, el 5 % de peores días. Peor día: {formato.pct(riesgo['peor_dia_pct'], 2)} el {fecha_str}.")

with col_der2:
    contrib = riesgo["contribucion_riesgo"]
    if not contrib.empty:
        top = contrib.idxmax()
        # En rojo: activos que aportan al riesgo mucho más que lo que pesan.
        desproporcionados = {t for t, c in contrib.items() if pesos.get(t) and c > 1.5 * pesos[t]}
        st.markdown(
            f"##### Riesgo: {top} aporta {formato.pct(contrib[top], 0)} con {formato.pct(pesos.get(top), 0)} del peso"
        )
        st.plotly_chart(
            charts.barras_horizontales(
                list(contrib.index), list(contrib.values), formato_pct=True,
                resaltar=desproporcionados, referencia=pesos,
            ),
            width="stretch",
        )
        st.caption(
            "Aporte de cada activo a la volatilidad total (entre paréntesis, su peso)."
            + (" En rojo: aportan más de 1,5 veces su peso." if desproporcionados else "")
        )

st.caption(riesgo["lectura_diversificacion"])
st.page_link("pages/9_Reporte.py", label="Ver el reporte completo con recomendaciones", icon="📄")

# ==================== Snapshot (el ETL ya guarda uno por día) ====================
st.divider()
with st.expander("📸 Guardar snapshot de hoy"):
    st.caption(
        "El ETL diario ya guarda una foto automática cada día hábil. Usá este botón solo si querés "
        "una foto ahora (por ejemplo, justo después de operar)."
    )
    if st.button("Guardar snapshot de hoy", type="primary"):
        from core.data_providers.ccl_provider import get_ccl_automatico

        ccl = get_ccl_automatico()
        if not ccl:
            st.error("No se pudo obtener el CCL para expresar el snapshot en USD. Probá de nuevo en unos minutos.")
            st.stop()
        snapshot = armar_snapshot(resumen, riesgo, pesos, ccl["valor"])
        get_repository().add_snapshot(snapshot)
        st.toast(
            f"Snapshot guardado: {formato_moneda(snapshot.valor_total_usd, 'USD')} al CCL {formato.fmt(ccl['valor'], ',.2f')}.",
            icon="📸",
        )
