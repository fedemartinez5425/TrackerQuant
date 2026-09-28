import json

import streamlit as st

from app_helpers import (
    formato_moneda,
    formato_pct,
    mostrar_ccl_sidebar,
    obtener_cartera_actual,
    obtener_historicos_riesgo,
    require_login,
)
from config.settings import settings
from core.portfolio.portfolio_engine import resumen_cartera
from core.risk.summary import calcular_resumen_riesgo
from core.storage import get_repository
from core.storage.models import PortfolioSnapshot
from core.viz import charts
from core.viz import palette as p

username = require_login()
mostrar_ccl_sidebar()

st.title("📊 Dashboard")
st.caption("Data Finance · Risk Analytics — vista general de la cartera, medida en USD equivalente para el riesgo y en pesos para el valor.")

posiciones = obtener_cartera_actual()
if not posiciones:
    st.info("Todavía no cargaste ninguna transacción. Andá a **Transacciones** para empezar.")
    st.stop()

resumen = resumen_cartera(posiciones)
pesos = {p_.ticker: p_.peso for p_ in posiciones if p_.peso}
historicos = obtener_historicos_riesgo(posiciones)

if historicos.empty:
    st.warning("No se pudo obtener histórico de precios en este momento para calcular el riesgo.")
    st.stop()

riesgo = calcular_resumen_riesgo(
    historicos, pesos, resumen["valor_actual_total"], settings.DEFAULT_BENCHMARK, settings.STRESS_SCENARIOS
)

# ==================== Semáforo (banner) ====================
color_semaforo = p.color_semaforo(riesgo["semaforo"])
st.markdown(
    f"""
    <div style="background:{color_semaforo}18; border:1px solid {color_semaforo}55;
    border-radius:12px; padding:0.85rem 1.2rem; margin-bottom:1rem; display:flex;
    justify-content:space-between; align-items:center;">
        <div>
            <span style="font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.15rem;
            color:{color_semaforo};">{riesgo['semaforo']}</span>
            <span style="color:{p.TEXT_SECONDARY}; font-size:0.85rem; margin-left:10px;">
            Volatilidad anualizada + concentración en las 2 posiciones más grandes</span>
        </div>
        <div style="font-family:'JetBrains Mono',monospace; color:{p.TEXT_SECONDARY}; font-size:0.8rem;">
        {resumen['cantidad_posiciones']} posiciones</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==================== KPIs ====================
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Valor Total", formato_moneda(resumen["valor_actual_total"]))
k2.metric(
    "Ganancia / Pérdida",
    formato_moneda(resumen["ganancia_perdida_total"]),
    delta=formato_pct(resumen["ganancia_perdida_pct_total"]),
)
k3.metric("Portfolio VaR (95%, 1 día)", formato_pct(riesgo["var_95_pct"]))
k4.metric("Expected Shortfall (95%)", formato_pct(riesgo["cvar_95_pct"]))
k5.metric("Volatilidad Anual", formato_pct(riesgo["volatilidad_anualizada"]))

st.divider()

# ==================== Fila 2: Evolución + Donut ====================
col_izq, col_der = st.columns([1.6, 1])
with col_izq:
    st.markdown("##### Evolución de la Cartera (base 100, pesos de HOY)")
    if not riesgo["indice_cartera"].empty:
        st.plotly_chart(charts.area_evolucion(riesgo["indice_cartera"]), width="stretch")
    else:
        st.info("Sin datos suficientes para graficar la evolución.")

with col_der:
    st.markdown("##### Exposición por Posición")
    st.plotly_chart(charts.donut_exposicion(pesos), width="stretch")

st.divider()

# ==================== Insights (compacto, reporte completo en su propia página) ====================
from core.insights.rules_engine import ICONO_SEVERIDAD, generar_insights  # noqa: E402

insights = generar_insights(riesgo, posiciones, settings.DEFAULT_BENCHMARK)
insights_relevantes = [i for i in insights if i.severidad in ("alto", "medio")][:3]

if insights_relevantes:
    st.markdown("##### 🔎 Principales señales")
    for i in insights_relevantes:
        st.markdown(f"{ICONO_SEVERIDAD[i.severidad]} **{i.categoria}** — {i.diagnostico}")
    st.page_link("pages/9_Reporte.py", label="Ver reporte completo con recomendaciones →", icon="📄")
else:
    st.success("Sin señales de alerta relevantes en este momento.")
    st.page_link("pages/9_Reporte.py", label="Ver reporte completo →", icon="📄")

st.divider()

# ==================== Fila 3: Histograma + Contribución al riesgo ====================
col_izq2, col_der2 = st.columns([1, 1])
with col_izq2:
    st.markdown("##### Distribución de Retornos Diarios")
    if not riesgo["retorno_cartera"].empty:
        st.plotly_chart(charts.histograma_retornos(riesgo["retorno_cartera"]), width="stretch")

with col_der2:
    st.markdown("##### Contribución al Riesgo por Activo")
    contrib = riesgo["contribucion_riesgo"]
    if not contrib.empty:
        st.plotly_chart(
            charts.barras_horizontales(list(contrib.index), list(contrib.values), formato_pct=True),
            width="stretch",
        )

st.caption(riesgo["lectura_diversificacion"])
if riesgo["peor_dia_pct"] is not None:
    fecha_str = riesgo["peor_dia_fecha"].date() if hasattr(riesgo["peor_dia_fecha"], "date") else riesgo["peor_dia_fecha"]
    st.caption(f"Peor día histórico de la cartera: {riesgo['peor_dia_pct']:.2%} el {fecha_str}.")

st.divider()

# ==================== Analytics histórico ====================
with st.expander("📸 Guardar snapshot de hoy (para analytics histórico)"):
    st.caption(
        "Guardá una 'foto' de hoy para construir con el tiempo una serie real que después "
        "puedas analizar — se guarda en tu backend de storage (CSV o Google Sheets)."
    )
    if st.button("Guardar snapshot", type="primary"):
        repo = get_repository()
        snapshot = PortfolioSnapshot(
            valor_total_usd=resumen["valor_actual_total"],
            cantidad_posiciones=resumen["cantidad_posiciones"],
            volatilidad_anualizada=riesgo["volatilidad_anualizada"],
            var_95_pct=riesgo["var_95_pct"],
            beta_vs_benchmark=riesgo["beta_cartera"],
            correlacion_promedio=riesgo["correlacion_ponderada"],
            composicion_json=json.dumps(pesos),
        )
        repo.add_snapshot(snapshot)
        st.success(f"Snapshot guardado para {snapshot.fecha}.")
