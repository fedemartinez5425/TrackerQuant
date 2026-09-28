import json

import pandas as pd
import streamlit as st

from app_helpers import formato_moneda, formato_pct, obtener_cartera_actual, obtener_historicos_riesgo, require_login
from config.settings import settings
from core.forecasting.backtest import tabla_backtest
from core.forecasting.returns_forecast import cono_incertidumbre, proyectar_retorno_acumulado, proyectar_valor_cartera
from core.forecasting.volatility_garch import resumen_forecast_volatilidad
from core.portfolio.portfolio_engine import resumen_cartera
from core.risk.volatility import retorno_diario_cartera
from core.storage import get_repository
from core.storage.models import PortfolioForecast
from core.viz import charts

username = require_login()

st.title("🔮 Forecasting")
st.caption(
    "Modelo GARCH(1,1) para pronosticar volatilidad, y un cono de incertidumbre para el valor de "
    "cartera basado en esa volatilidad. No es un pronóstico de precios ni de dirección de mercado."
)

posiciones = obtener_cartera_actual()
if not posiciones:
    st.info("Todavía no cargaste ninguna transacción.")
    st.stop()

resumen = resumen_cartera(posiciones)
pesos = {p.ticker: p.peso for p in posiciones if p.peso}
historicos = obtener_historicos_riesgo(posiciones, period="2y")

if historicos.empty or len(historicos) < 120:
    st.warning("Se necesita al menos ~6 meses de histórico de precios para que el modelo GARCH converja de forma confiable.")
    st.stop()

retornos = historicos.pct_change().dropna(how="all")
retorno_cartera = retorno_diario_cartera(retornos, pesos)

horizonte_dias = st.slider("Horizonte de forecast (días hábiles)", min_value=5, max_value=30, value=10, step=5)

tab_vol, tab_retornos, tab_backtest = st.tabs(["📉 Volatilidad (GARCH)", "📈 Cono de Retornos", "🎯 Precisión Histórica"])

resumen_vol = resumen_forecast_volatilidad(retorno_cartera, horizonte_dias)

# ==================== TAB 1: VOLATILIDAD ====================
with tab_vol:
    if resumen_vol is None:
        st.warning("No hay suficientes datos para ajustar el modelo GARCH sobre esta cartera.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Volatilidad condicional (hoy)", formato_pct(resumen_vol["vol_actual"]))
        c2.metric(f"Pronóstico a {horizonte_dias}d", formato_pct(resumen_vol["vol_n_dias"]))
        c3.metric("Promedio histórico", formato_pct(resumen_vol["vol_promedio_historico"]))
        c4.metric("Régimen actual", "")
        st.markdown(f"##### {resumen_vol['regimen']}")

        st.plotly_chart(
            charts.linea_volatilidad_forecast(
                resumen_vol["vol_realizada_movil"], resumen_vol["vol_condicional_historica"], resumen_vol["forecast_path"],
            ),
            width="stretch",
        )

        with st.expander("¿Cómo funciona el modelo? (sin caja negra)"):
            st.markdown(
                f"""
GARCH(1,1) modela la varianza de HOY como una combinación de: una constante (`omega`), el
shock de ayer al cuadrado (`alpha`) y la varianza de ayer (`beta`). Es el modelo estándar de la
industria para esto porque captura el "clustering" de volatilidad (períodos calmos y turbulentos
se agrupan) — algo que un promedio móvil simple no ve.

**Parámetros ajustados a tu cartera:** ω={resumen_vol['parametros']['omega']:.4f},
α={resumen_vol['parametros']['alpha']:.4f}, β={resumen_vol['parametros']['beta']:.4f}
(α+β cercano a 1 = la volatilidad es muy persistente, tarda en volver a su promedio).

**Limitación honesta:** el modelo asume que el patrón de volatilidad pasado se mantiene — no
anticipa shocks nuevos (una noticia, un cambio de política). Es un pronóstico estadístico, no una
bola de cristal.
                """
            )

        if st.button("💾 Guardar este forecast (para medir precisión después)"):
            repo = get_repository()
            forecast = PortfolioForecast(
                horizonte_dias=horizonte_dias,
                vol_pronosticada_anual=resumen_vol["vol_n_dias"],
                composicion_json=json.dumps(pesos),
            )
            repo.add_forecast(forecast)
            st.success(f"Forecast guardado. Volvé en ~{horizonte_dias} días hábiles para ver qué tan preciso fue en la pestaña 'Precisión Histórica'.")

# ==================== TAB 2: CONO DE RETORNOS ====================
with tab_retornos:
    st.warning(
        "⚠️ **Esto NO predice si tu cartera va a subir o bajar.** Los retornos de corto plazo no son "
        "pronosticables de forma confiable (mercados razonablemente eficientes) — lo que sí se puede "
        "estimar es el RANGO probable de resultados, combinando la deriva histórica con la volatilidad "
        "pronosticada. Es un cono de incertidumbre, no una predicción de dirección."
    )
    if resumen_vol is None:
        st.info("Necesita el forecast de volatilidad de la pestaña anterior.")
    else:
        proyeccion = proyectar_retorno_acumulado(retorno_cartera, horizonte_dias, resumen_vol["vol_n_dias"])
        proyeccion_dinero = proyectar_valor_cartera(proyeccion, resumen["valor_actual_total"])

        c1, c2, c3 = st.columns(3)
        c1.metric(f"Valor esperado a {horizonte_dias}d", formato_moneda(proyeccion_dinero["retorno_esperado_pct"]))
        c2.metric("Banda 68% (± 1σ)", f"{formato_moneda(proyeccion_dinero['banda_68_inf'])} — {formato_moneda(proyeccion_dinero['banda_68_sup'])}")
        c3.metric("Banda 95% (± 2σ)", f"{formato_moneda(proyeccion_dinero['banda_95_inf'])} — {formato_moneda(proyeccion_dinero['banda_95_sup'])}")

        cono_df = cono_incertidumbre(retorno_cartera, resumen_vol["forecast_path"], resumen["valor_actual_total"])
        indice_valor = (1 + retorno_cartera).cumprod() * resumen["valor_actual_total"] / (1 + retorno_cartera).cumprod().iloc[-1]
        st.plotly_chart(charts.cono_forecast(indice_valor, cono_df, nombre_historico="Valor de cartera (reescalado a hoy)"), width="stretch")

# ==================== TAB 3: PRECISIÓN HISTÓRICA (BACKTEST) ====================
with tab_backtest:
    st.caption(
        "Compara los forecasts de volatilidad que guardaste en el pasado contra lo que realmente "
        "pasó, recalculado con los mismos pesos que tenía tu cartera en ese momento."
    )
    repo = get_repository()
    forecasts_guardados = repo.list_forecasts()

    if not forecasts_guardados:
        st.info("Todavía no guardaste ningún forecast. Guardalo desde la pestaña de Volatilidad y volvé después de que pase el horizonte.")
    else:
        from app_helpers import obtener_instrumentos

        instrumentos = obtener_instrumentos()
        df_backtest = tabla_backtest(forecasts_guardados, instrumentos)

        pendientes = len(forecasts_guardados) - len(df_backtest)
        if pendientes > 0:
            st.caption(f"{pendientes} forecast(s) todavía no llegaron a su horizonte — se evalúan automáticamente cuando corresponda.")

        if df_backtest.empty:
            st.info("Ningún forecast guardado llegó todavía a su fecha de horizonte.")
        else:
            mae = df_backtest["error_pp"].abs().mean()
            st.metric("Error absoluto promedio (MAE)", f"{mae:.2f} puntos porcentuales")
            st.dataframe(
                df_backtest.style.format(
                    {"vol_pronosticada": "{:.2%}", "vol_realizada": "{:.2%}", "error_pp": "{:+.2f} pp"}
                ),
                width="stretch", hide_index=True,
            )
            st.caption("Error positivo = el modelo subestimó la volatilidad real. Error negativo = la sobreestimó.")
