"""
Evolución real: cuánto valió tu cartera día por día con lo que tenías ese
día, cuánta plata pusiste, cuánto ganó el mercado y tu rendimiento sin el
efecto de los aportes, contra el SPY y el dólar CCL.
Lógica en core/portfolio/evolucion.py.
"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app_helpers import mostrar_ccl_sidebar, mostrar_frescura, obtener_evolucion, require_login, tarjeta_alerta
from config.settings import settings
from core.portfolio.evolucion import referencias
from core.viz import charts, formato
from core.viz import palette as p

require_login()
mostrar_ccl_sidebar()

st.title("📆 Evolución real")
st.caption("Tu cartera día por día con lo que tenías cada día, a partir de tus compras y ventas.")
mostrar_frescura()

evo, precios = obtener_evolucion()
if evo is None or evo.vacia:
    st.info("Todavía no hay operaciones: cargá o importá tus compras y la historia se arma sola.")
    c1, c2 = st.columns(2)
    c1.page_link("pages/3_Transacciones.py", label="Cargar una compra a mano", icon="📝")
    c2.page_link("pages/7_Importar_Broker.py", label="Importar el CSV del broker", icon="📥")
    st.stop()

# ---------------- Controles: una fila arriba de todo ----------------
hoy = date.today()
PERIODOS = {
    "Todo": None,
    "1 año": hoy - timedelta(days=365),
    "Este año": date(hoy.year, 1, 1),
    "6 meses": hoy - timedelta(days=182),
    "3 meses": hoy - timedelta(days=91),
    "1 mes": hoy - timedelta(days=30),
}
c_mon, c_per = st.columns([1, 3])
moneda = c_mon.segmented_control("Moneda", ["ARS", "USD"], default="ARS",
                                 format_func=lambda m: "Pesos" if m == "ARS" else "Dólares CCL",
                                 help="En dólares: cada día se divide por el CCL de ese día.") or "ARS"
nombre_periodo = c_per.segmented_control("Período", list(PERIODOS), default="Todo") or "Todo"
desde = PERIODOS[nombre_periodo]

if moneda == "USD" and evo.diario["valor_usd"].isna().all():
    st.warning("No hay CCL histórico para pasar a dólares en este momento: se muestra en pesos.")
    moneda = "ARS"

m = moneda.lower()
r = evo.resumen(moneda, desde)
d = evo.diario if not r else evo.diario.loc[evo.diario.index >= pd.Timestamp(r["desde"])]
dec = 0 if moneda == "ARS" else 2
# El período elegido puede empezar antes de tu primera compra: entonces es "todo".
recortado = r["desde"] > evo.diario.index[0].date()

# ---------------- Alertas de datos (split / ratio / sin precio) ----------------
for a in evo.alertas[:5]:
    tarjeta_alerta("alto" if a.tipo != "sin_precio" else "medio", a.detalle,
                   titulo="Revisá esta operación" if a.tipo != "sin_precio" else "Sin precio de mercado")
if len(evo.alertas) > 5:
    st.caption(f"…y {len(evo.alertas) - 5} avisos más.")

# ---------------- KPIs ----------------
refs = referencias(evo, precios, moneda, desde)
rend = r.get("rendimiento")
bench = settings.DEFAULT_BENCHMARK
rend_bench = (refs[bench].dropna().iloc[-1] / 100 - 1) if bench in refs and refs[bench].notna().any() else None
rend_dolar = (refs["Dólar CCL"].iloc[-1] / 100 - 1) if "Dólar CCL" in refs else None

k1, k2, k3, k4 = st.columns(4)
k1.metric("Valor hoy", formato.moneda(r["valor_final"], moneda, dec),
          help="Cantidades de hoy × último precio de BCBA.")
k2.metric("Plata que pusiste" if not recortado else f"Aportes netos ({nombre_periodo.lower()})",
          formato.moneda(r["aportes_netos"], moneda, dec),
          help="Compras (con comisión) menos ventas. Sin cuenta de efectivo: una venta cuenta como plata que sacaste."
               + ("" if not recortado else f" El período arranca con {formato.moneda(r['valor_inicial'], moneda, dec)} en la cartera."))
k3.metric("Ganancia por mercado", formato.moneda(r["ganancia"], moneda, dec),
          delta=formato.pct(r["ganancia"] / (r["valor_inicial"] + max(r["aportes_netos"], 0)), 1, signo=True)
          if (r["valor_inicial"] + max(r["aportes_netos"], 0)) > 0 else None,
          help="Valor final − valor inicial − aportes netos: lo que ganaste (o perdiste) por los precios, no por poner plata.")
comparacion = []
if rend is not None and rend_bench is not None:
    comparacion.append(f"{formato.fmt((rend - rend_bench) * 100, '+.1f')} pp vs {bench}")
k4.metric("Rendimiento (sin aportes)", formato.pct(rend, 1, signo=True) if rend is not None else "—",
          delta=comparacion[0] if comparacion else None,
          help="Time-weighted: encadena los rendimientos diarios descontando compras y ventas. Es el número "
               "comparable con un índice. No está anualizado.")

base_ganancia = r["valor_inicial"] + max(r["aportes_netos"], 0)
if rend is not None and base_ganancia > 0 and abs(rend - r["ganancia"] / base_ganancia) > 0.05:
    st.caption(
        "ℹ️ El rendimiento y la ganancia no coinciden porque la plata entró en distintos momentos: el rendimiento mide "
        "cuánto rindió cada peso desde el inicio; la ganancia, cuánto ganó toda la plata que pusiste (mucha entró hace poco)."
    )

veredictos = []
if rend is not None and rend_bench is not None:
    veredictos.append(f"{'🟢 le ganaste' if rend >= rend_bench else '🔴 perdiste contra'} el {bench} "
                      f"({formato.pct(rend_bench, 1, signo=True)})")
if rend is not None and rend_dolar is not None:
    veredictos.append(f"{'🟢 le ganaste' if rend >= rend_dolar else '🔴 perdiste contra'} el dólar CCL "
                      f"({formato.pct(rend_dolar, 1, signo=True)})")
if veredictos:
    st.markdown(f"**{nombre_periodo}:** " + " · ".join(veredictos))

# ---------------- Gráfico 1: valor vs plata puesta ----------------
st.divider()
aportes_linea = d[f"aportes_{m}"] - (d[f"aportes_{m}"].iloc[0] - r["valor_inicial"] if recortado else 0)
ganancia = r["ganancia"]
titulo_valor = (
    f"{'Ganaste' if ganancia >= 0 else 'Perdiste'} {formato.moneda(abs(ganancia), moneda, dec)} "
    f"sobre {formato.moneda(r['valor_inicial'] + r['aportes_netos'], moneda, dec)} puestos"
)
st.markdown("##### " + titulo_valor.replace("$", r"\$"))  # sin escapar, "$ … $" se lee como LaTeX
st.caption("Línea punteada: la plata que pusiste (en el período, arranca con el valor inicial). "
           "▲ compra · ▼ venta: pasá el mouse para ver el detalle.")
st.plotly_chart(charts.valor_vs_aportes(d[f"valor_{m}"], aportes_linea, evo.operaciones, moneda), width="stretch")

# ---------------- Gráfico 2: rendimiento vs referencias ----------------
indice = evo.indice(moneda, desde)
if not indice.empty:
    tabla = pd.concat([indice.rename("Tu cartera"), refs], axis=1)
    titulo = f"Tu rendimiento: {formato.pct(rend, 1, signo=True)}"
    if rend_bench is not None:
        titulo += f" vs {bench} {formato.pct(rend_bench, 1, signo=True)}"
    if rend_dolar is not None:
        titulo += f" y dólar CCL {formato.pct(rend_dolar, 1, signo=True)}"
    st.markdown(f"##### {titulo}")
    st.caption("Base 100 al inicio del período. Las compras y ventas no mueven la línea: solo los precios.")
    fig = charts.linea_multi(tabla)
    # Tu cartera en el color principal; las referencias en gris punteado.
    fig.for_each_trace(lambda t: t.update(line=dict(color=p.TEXT_SECONDARY, dash="dot", width=1.6))
                       if t.name != "Tu cartera" else t.update(line=dict(color=p.ACCENT, width=2.4)))
    fig.update_xaxes(tickformat="%m/%Y", dtick="M1")
    st.plotly_chart(fig, width="stretch")

# ---------------- Gráfico 3: composición ----------------
pesos = evo.pesos.loc[evo.pesos.index >= d.index[0]]
if not pesos.empty and pesos.iloc[-1].sum() > 0:
    ultimo = pesos.iloc[-1].sort_values(ascending=False)
    primero = pesos.iloc[0]
    mayor = ultimo.index[0]
    st.markdown(
        f"##### Composición: hoy {mayor} pesa {formato.pct(ultimo.iloc[0], 0)}"
        + (f" (al inicio del período, {formato.pct(primero.get(mayor, 0), 0)})" if recortado else "")
    )
    st.plotly_chart(charts.composicion_en_el_tiempo(pesos), width="stretch")

# ---------------- Detalle ----------------
with st.expander("Ver las operaciones"):
    ops = evo.operaciones.sort_values("fecha", ascending=False)
    st.dataframe(
        pd.DataFrame({
            "Fecha": ops["fecha_original"],
            "Ticker": ops["ticker"],
            "Operación": ops["accion"].str.capitalize(),
            "Cantidad": ops["cantidad"],
            "Precio": ops["precio"],
            "Moneda": ops["moneda"],
            "Flujo $": ops["monto_ars"],
            "Flujo US$": ops["monto_usd"],
        }),
        hide_index=True, width="stretch",
        column_config={
            "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Cantidad": st.column_config.NumberColumn(format="localized"),
            "Precio": st.column_config.NumberColumn(format="localized"),
            "Flujo $": st.column_config.NumberColumn(format="localized", help="+ pusiste · − sacaste"),
            "Flujo US$": st.column_config.NumberColumn(format="localized"),
        },
    )

st.caption(
    "Cómo se calcula: precio de cierre en BCBA (CEDEARs sin cotización: ADR / ratio × CCL); días sin cotización con el "
    "último precio. Precios ajustados por dividendos, así que los dividendos quedan dentro del rendimiento. "
    "Sin cuenta de efectivo: vender es sacar plata de la cartera. Cada operación se toma al cierre de su día."
)
