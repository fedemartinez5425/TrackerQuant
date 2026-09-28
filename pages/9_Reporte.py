import streamlit as st

from app_helpers import obtener_cartera_actual, obtener_historicos_riesgo, require_login
from config.settings import settings
from core.insights.rules_engine import ICONO_SEVERIDAD, generar_insights, generar_reporte_markdown
from core.portfolio.portfolio_engine import resumen_cartera
from core.risk.summary import calcular_resumen_riesgo

username = require_login()

st.title("📄 Reporte Ejecutivo")
st.caption(
    "Diagnóstico y recomendaciones generadas por reglas cuantitativas a partir de tu cartera actual — "
    "pensado como punto de partida para llevar a una IA (o a tu propia research) y profundizar."
)

posiciones = obtener_cartera_actual()
if not posiciones:
    st.info("Todavía no cargaste ninguna transacción.")
    st.stop()

resumen = resumen_cartera(posiciones)
pesos = {p.ticker: p.peso for p in posiciones if p.peso}
historicos = obtener_historicos_riesgo(posiciones)

if historicos.empty:
    st.warning("No se pudo obtener histórico de precios en este momento para generar el reporte.")
    st.stop()

riesgo = calcular_resumen_riesgo(
    historicos, pesos, resumen["valor_actual_total"], settings.DEFAULT_BENCHMARK, settings.STRESS_SCENARIOS
)
insights = generar_insights(riesgo, posiciones, settings.DEFAULT_BENCHMARK)

# ==================== Resumen visual (antes del markdown) ====================
col1, col2, col3 = st.columns(3)
col1.metric("Semáforo", riesgo["semaforo"])
col2.metric("Alertas activas", len([i for i in insights if i.severidad == "alto"]))
col3.metric("A vigilar", len([i for i in insights if i.severidad == "medio"]))

for i in sorted(insights, key=lambda x: {"alto": 0, "medio": 1, "bajo": 2, "info": 2}[x.severidad]):
    icono = ICONO_SEVERIDAD[i.severidad]
    with st.expander(f"{icono} {i.categoria} — {i.diagnostico}", expanded=(i.severidad == "alto")):
        st.write(i.recomendacion)

st.divider()

# ==================== Reporte completo en Markdown ====================
st.subheader("Reporte completo (Markdown)")
st.caption("Copialo y pegalo en tu IA de preferencia para seguir investigando, o descargalo.")

reporte_md = generar_reporte_markdown(riesgo, posiciones, resumen, settings.DEFAULT_BENCHMARK)

st.download_button(
    "⬇️ Descargar reporte (.md)",
    data=reporte_md,
    file_name=f"reporte_riesgo_{resumen['cantidad_posiciones']}pos.md",
    mime="text/markdown",
)

with st.expander("📋 Ver / copiar el texto completo", expanded=False):
    st.text_area("Reporte en Markdown", value=reporte_md, height=400, label_visibility="collapsed")

st.markdown(reporte_md)
