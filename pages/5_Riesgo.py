import pandas as pd
import streamlit as st

from app_helpers import formato_moneda, obtener_cartera_actual, obtener_historicos_riesgo, require_login
from config.settings import settings
from core.portfolio.portfolio_engine import resumen_cartera
from core.risk.correlation import (
    correlacion_promedio_ponderada,
    correlacion_promedio_simple,
    lectura_diversificacion,
    matriz_correlacion,
)
from core.risk.stress_test import beta_ponderado_cartera, betas_por_activo, escenarios_estres
from core.risk.var import peor_dia_historico, resumen_var_cvar
from core.risk.volatility import indice_base_100, retorno_diario_cartera, volatilidad_anualizada
from core.viz import charts

username = require_login()

st.title("⚠️ Riesgo")
st.caption("Volatilidad, VaR/CVaR, correlación y escenarios de estrés — todo medido en USD equivalente para que CEDEARs y acciones argentinas sean comparables.")

posiciones = obtener_cartera_actual()
if not posiciones:
    st.info("Todavía no cargaste ninguna transacción.")
    st.stop()

pesos = {p.ticker: p.peso for p in posiciones if p.peso}
resumen = resumen_cartera(posiciones)
historicos = obtener_historicos_riesgo(posiciones)

if historicos.empty:
    st.warning("No se pudo obtener histórico de precios para calcular riesgo en este momento.")
    st.stop()

retornos = historicos.pct_change().dropna(how="all")
retorno_cartera = retorno_diario_cartera(retornos, pesos)

tab_var, tab_corr, tab_estres = st.tabs(["📉 Volatilidad, VaR y CVaR", "🔗 Correlación", "💥 Estrés"])

# ==================== TAB 1: VOLATILIDAD, VAR, CVAR ====================
with tab_var:
    indice = indice_base_100(retorno_cartera)
    vol_anual = volatilidad_anualizada(retorno_cartera)
    peor_pct, peor_fecha = peor_dia_historico(retorno_cartera)

    c1, c2, c3 = st.columns(3)
    c1.metric("Volatilidad Anualizada", f"{vol_anual:.1%}" if vol_anual else "—")
    c2.metric("Retorno diario promedio", f"{retorno_cartera.mean():.3%}" if not retorno_cartera.empty else "—")
    c3.metric(
        "Peor día histórico", f"{peor_pct:.2%}" if peor_pct is not None else "—",
        help=f"Ocurrió el {peor_fecha.date() if hasattr(peor_fecha, 'date') else peor_fecha}" if peor_fecha is not None else None,
    )

    st.markdown("##### Evolución de $100 invertidos con los pesos de HOY (USD equivalente)")
    if not indice.empty:
        st.plotly_chart(charts.area_evolucion(indice), width="stretch")

    st.markdown("##### Distribución de Retornos Diarios")
    if not retorno_cartera.empty:
        st.plotly_chart(charts.histograma_retornos(retorno_cartera), width="stretch")

    st.divider()
    st.subheader("Value at Risk (VaR) y CVaR (Expected Shortfall)")
    st.caption(
        "VaR histórico: el peor retorno diario observado, al nivel de confianza indicado. "
        "CVaR: el promedio de las pérdidas en ese peor tramo de días."
    )
    filas = resumen_var_cvar(retorno_cartera, resumen["valor_actual_total"])
    df_var = pd.DataFrame(filas)
    st.dataframe(
        df_var.style.format(
            {
                "VaR Histórico %": "{:.2%}",
                "VaR Histórico $": "$ {:,.2f}",
                "CVaR (Expected Shortfall) %": "{:.2%}",
                "CVaR (Expected Shortfall) $": "$ {:,.2f}",
            },
            na_rep="—",
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Con 95% de confianza, en un día normal no deberías perder más que el VaR. El 5% restante "
        "de los días, la pérdida promedio es el CVaR — y puede ser bastante peor."
    )

# ==================== TAB 2: CORRELACIÓN ====================
with tab_corr:
    tickers = [t for t in pesos if t in historicos.columns]
    if len(tickers) < 2:
        st.info("Necesitás al menos 2 posiciones distintas para calcular correlación.")
    else:
        matriz = matriz_correlacion(retornos[tickers])
        st.plotly_chart(charts.heatmap_correlacion(matriz), width="stretch")

        corr_simple = correlacion_promedio_simple(matriz)
        corr_ponderada = correlacion_promedio_ponderada(matriz, pesos)

        c1, c2 = st.columns(2)
        c1.metric("Correlación promedio (simple)", f"{corr_simple:.2f}" if corr_simple is not None else "—")
        c2.metric("Correlación promedio (ponderada)", f"{corr_ponderada:.2f}" if corr_ponderada is not None else "—")

        st.markdown(f"##### {lectura_diversificacion(corr_ponderada if corr_ponderada is not None else corr_simple)}")
        st.caption(
            "La ponderada pesa más la correlación entre tus posiciones más grandes: dos activos "
            "chicos correlacionados preocupan menos que si pasa entre tus dos posiciones top."
        )

# ==================== TAB 3: ESTRÉS ====================
with tab_estres:
    st.caption(
        f"Modelo de un solo factor: estima el impacto usando el Beta de cada activo contra el "
        f"benchmark ({settings.DEFAULT_BENCHMARK}). No captura shocks propios de cada activo ni el "
        f"hecho de que las correlaciones suelen dispararse en las crisis."
    )
    if settings.DEFAULT_BENCHMARK not in historicos.columns:
        st.warning(f"No se pudo obtener histórico del benchmark ({settings.DEFAULT_BENCHMARK}) en este momento.")
    else:
        betas = betas_por_activo(retornos, settings.DEFAULT_BENCHMARK)
        beta_cartera = beta_ponderado_cartera(betas, pesos)

        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"##### Sensibilidad de cada activo al {settings.DEFAULT_BENCHMARK}")
            if betas:
                st.plotly_chart(
                    charts.barras_horizontales(list(betas.keys()), list(betas.values()), formato_pct=False),
                    width="stretch",
                )
        with col2:
            st.metric(f"Beta ponderado vs. {settings.DEFAULT_BENCHMARK}", f"{beta_cartera:.2f}" if beta_cartera else "—")

        st.divider()
        st.markdown("##### Escenarios de shock")
        filas_estres = escenarios_estres(beta_cartera, resumen["valor_actual_total"], shocks=settings.STRESS_SCENARIOS)
        st.plotly_chart(charts.barras_escenarios_estres(filas_estres), width="stretch")
        df_escenarios = pd.DataFrame(filas_estres)
        st.dataframe(
            df_escenarios.style.format(
                {"Shock Benchmark": "{:.0%}", "Impacto Estimado %": "{:.1%}", "Impacto Estimado $": "$ {:,.2f}"},
                na_rep="—",
            ),
            width="stretch",
            hide_index=True,
        )
