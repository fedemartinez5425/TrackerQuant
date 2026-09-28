import streamlit as st

from app_helpers import mostrar_ccl_sidebar, obtener_cartera_actual, require_login
from core.portfolio.portfolio_engine import cartera_a_dataframe
from core.viz import charts

username = require_login()
mostrar_ccl_sidebar()

st.title("💼 Cartera — Posiciones Actuales")
st.caption("Costo promedio ponderado (no FIFO/LIFO), recalculado a partir de todas las transacciones. Valores en pesos ($ ARS).")

posiciones = obtener_cartera_actual()

if not posiciones:
    st.info("Todavía no cargaste ninguna transacción. Andá a **Transacciones** para empezar.")
    st.stop()

col_tabla, col_donut = st.columns([2, 1])

with col_tabla:
    df = cartera_a_dataframe(posiciones)
    st.dataframe(
        df.style.format(
            {
                "Cantidad": "{:,.4f}",
                "Costo Promedio": "$ {:,.2f}",
                "Precio BCBA": "$ {:,.2f}",
                "Precio Teórico (CCL)": "$ {:,.2f}",
                "Precio Final": "$ {:,.2f}",
                "Prima/Desc. %": "{:.1%}",
                "Valor Actual": "$ {:,.2f}",
                "Valor Invertido": "$ {:,.2f}",
                "Peso %": "{:.1%}",
                "G/P $": "$ {:,.2f}",
                "G/P %": "{:.1%}",
            },
            na_rep="—",
        ),
        width="stretch",
        hide_index=True,
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
        """
    )
