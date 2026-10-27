import streamlit as st

from app_helpers import formato_moneda, formato_pct, mostrar_ccl_sidebar, obtener_cartera_actual, require_login
from core.portfolio.portfolio_engine import cartera_a_dataframe, resumen_cartera
from core.viz import charts, semaforos

FORMATOS_CARTERA = {
    "Cantidad": "{:,.4f}",
    "Costo Promedio": "$ {:,.2f}",
    "Precio BCBA": "$ {:,.2f}",
    "Precio Teórico (CCL)": "$ {:,.2f}",
    "Precio Final": "$ {:,.2f}",
    "Prima/Desc. %": "{:.1%}",
    "Valor Actual": "$ {:,.2f}",
    "Valor Invertido": "$ {:,.2f}",
    "G/P $": "$ {:,.2f}",
    "G/P %": "{:.1%}",
    "Invertido US$": "US$ {:,.2f}",
    "Valor Actual US$": "US$ {:,.2f}",
    "G/P US$": "US$ {:,.2f}",
    "G/P US$ %": "{:.1%}",
}  # "Peso %" no: lo formatea su ProgressColumn
REGLAS_CARTERA = {
    "Prima/Desc. %": "prima",
    "G/P $": "signo", "G/P %": "signo", "G/P US$": "signo", "G/P US$ %": "signo",
}

username = require_login()
mostrar_ccl_sidebar()

st.title("💼 Cartera — Posiciones Actuales")
st.caption("Costo promedio ponderado (no FIFO/LIFO), recalculado a partir de todas las transacciones. Valores en pesos ($ ARS).")

posiciones = obtener_cartera_actual()

if not posiciones:
    st.info("Todavía no cargaste ninguna transacción.")
    st.page_link("pages/3_Transacciones.py", label="Cargar tu primera compra", icon="📝")
    st.stop()

resumen = resumen_cartera(posiciones)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Valor Actual", formato_moneda(resumen["valor_actual_total"]))
m2.metric(
    "G/P en pesos",
    formato_moneda(resumen["ganancia_perdida_total"]),
    delta=formato_pct(resumen["ganancia_perdida_pct_total"]),
)
m3.metric("Valor Actual US$ (CCL hoy)", formato_moneda(resumen["valor_actual_usd_total"], "USD"))
m4.metric(
    "G/P en USD-CCL",
    formato_moneda(resumen["ganancia_perdida_usd_total"], "USD"),
    delta=formato_pct(resumen["ganancia_perdida_usd_pct_total"]),
)

col_tabla, col_donut = st.columns([2, 1])

with col_tabla:
    df = cartera_a_dataframe(posiciones)
    # La señal es de RIESGO (concentración y prima del CEDEAR), no de G/P: perder
    # plata en una posición no la vuelve riesgosa.
    df.insert(1, "Señal", semaforos.columna_senal(df, {"Peso %": "peso", "Prima/Desc. %": "prima"}))
    ver_todo = st.toggle("Ver todas las columnas (precios, costo, US$)", value=False)
    if not ver_todo:
        df = df[["Ticker", "Señal", "Peso %", "Valor Actual", "G/P $", "G/P %", "G/P US$", "G/P US$ %"]]
    st.dataframe(
        semaforos.tabla(df, FORMATOS_CARTERA, REGLAS_CARTERA),
        width="stretch",
        hide_index=True,
        column_config={
            "Peso %": st.column_config.ProgressColumn(
                "Peso %", min_value=0.0, max_value=1.0, format="percent",
                help=f"🟡 más de {semaforos.PESO_MEDIO:.0%} · 🔴 más de {semaforos.PESO_ALTO:.0%} de la cartera.",
            ),
        },
    )
    st.caption(
        f"{semaforos.LEYENDA}. Señal = riesgo de la posición: peso (🟡 > {semaforos.PESO_MEDIO:.0%}, "
        f"🔴 > {semaforos.PESO_ALTO:.0%}) y prima del CEDEAR vs. su teórico (🟡 > ±{semaforos.PRIMA_MEDIA:.0%}, "
        f"🔴 > ±{semaforos.PRIMA_ALTA:.0%}). G/P en verde o rojo según gane o pierda."
    )

with col_donut:
    pesos = {p.ticker: p.peso for p in posiciones if p.peso}
    if pesos:
        st.plotly_chart(charts.donut_exposicion(pesos), width="stretch")

with st.expander("¿Cómo se calcula esto? (todo automático, sin cargar nada a mano)"):
    st.markdown(
        """
- **Acción ARG** (ej: PAMP, GGAL comprada directo): Precio Final = Precio BCBA. No aplica
  ratio ni CCL — es una acción en pesos, sin conversión.
- **CEDEAR** (ej: AMZN): Precio BCBA si está disponible; si no, cae al Precio Teórico
  (`precio ADR (USD) / ratio × CCL automático`) como fallback.
- **Ratio CEDEAR**: se autocompleta desde el listado oficial de Comafi al cargar la
  transacción (ver ⚙️ Configuración para actualizar el cache).
- **Prima/Desc. %** (solo CEDEARs): diferencia entre el precio real de mercado (BCBA) y
  el teórico. Si supera ±3%, sospechá de iliquidez antes de confiar en el número.
- **Costo Promedio**: se recalcula con cada compra/venta usando costo promedio ponderado.
- **G/P en USD-CCL**: cada compra se pasa a dólares con el CCL de **su fecha** (las cargadas
  en USD se toman tal cual) y se compara con el valor actual / CCL de **hoy**. Las ventas
  descuentan el costo en USD a costo promedio, igual que en pesos. Muestra si le ganaste
  al dólar, no solo a los pesos.
        """
    )
