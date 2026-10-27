import pandas as pd
import streamlit as st

from app_helpers import (
    formato_moneda,
    formato_pct,
    invalidar_caches,
    mostrar_ccl_sidebar,
    obtener_cartera_actual,
    obtener_historicos_decision,
    obtener_precio_unidad,
    obtener_watchlist,
    require_login,
)
from config.settings import settings
from core.decision.candidatos import (
    PESO_OBJETIVO_DEFAULT,
    evaluar_candidato,
    peso_de_una_unidad,
    rankear_candidatos,
    unidades_para_peso,
)
from core.performance.metrics import metricas_cartera, metricas_por_activo
from core.portfolio.portfolio_engine import resumen_cartera
from core.storage import get_repository
from core.storage.models import AuditEvent, TipoInstrumento, WatchlistItem
from core.viz import semaforos

username = require_login()
mostrar_ccl_sidebar()

st.title("🎯 Candidatos")
st.caption(
    f"Qué pasaría con la cartera si sumás un activo de tu watchlist. Todo en USD equivalente, "
    f"con {settings.HISTORY_PERIOD_DECISION} de historia y tasa libre de riesgo de "
    f"{settings.RISK_FREE_RATE:.1%} anual."
)
st.warning(
    "**Ojo con el sesgo de supervivencia:** esto es un backtest. Los candidatos que mirás "
    "suelen ser los que ya subieron, y el pasado no garantiza nada. Usalo para comparar riesgo "
    "y diversificación, no como predicción. Lo cualitativo (noticias, gestión, balances) queda afuera.",
    icon="⚠️",
)

repo = get_repository()
posiciones = obtener_cartera_actual()
watchlist = obtener_watchlist()

# ==================== WATCHLIST ====================
st.subheader("Watchlist")
col_alta, col_lista = st.columns([1, 1])

with col_alta:
    with st.form("alta_watchlist", clear_on_submit=True):
        st.markdown("**Agregar candidato**")
        ticker = st.text_input("Ticker BCBA", placeholder="META").strip().upper()
        tipo = st.selectbox("Tipo", [t.value for t in TipoInstrumento], index=1)
        ticker_usd = st.text_input("Ticker del ADR (solo CEDEAR)", placeholder="META").strip().upper()
        ratio = st.number_input(
            "Ratio CEDEAR (opcional)", min_value=0.0, value=0.0, step=1.0,
            help="X CEDEARs = 1 ADR. Si lo dejás en 0 se busca en el listado de Comafi.",
        )
        notas = st.text_input("Notas", placeholder="Por qué lo estás mirando")
        if st.form_submit_button("Agregar", type="primary"):
            try:
                es_cedear = tipo == TipoInstrumento.CEDEAR.value
                item = WatchlistItem(
                    ticker=ticker,
                    tipo_instrumento=TipoInstrumento(tipo),
                    ticker_usd=(ticker_usd or ticker) if es_cedear else None,
                    ratio_cedear=(ratio or None) if es_cedear else None,
                    notas=notas,
                )
                repo.upsert_watchlist_item(item)
                repo.add_audit_event(AuditEvent(usuario=username, accion="ALTA_WATCHLIST", detalle=item.ticker))
                invalidar_caches()
                st.rerun()
            except ValueError as exc:
                st.error(f"No se pudo agregar: {exc}")

with col_lista:
    if watchlist:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Ticker": i.ticker,
                        "Tipo": i.tipo_instrumento.value,
                        "ADR": i.ticker_usd or "—",
                        "Ratio": i.ratio_cedear,
                        "Notas": i.notas,
                    }
                    for i in watchlist
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        a_borrar = st.selectbox("Sacar de la watchlist", [i.ticker for i in watchlist])
        if st.button("Sacar"):
            if repo.remove_watchlist_item(a_borrar):
                repo.add_audit_event(AuditEvent(usuario=username, accion="BAJA_WATCHLIST", detalle=a_borrar))
            invalidar_caches()
            st.rerun()
    else:
        st.info("Tu watchlist está vacía. Agregá un ticker para evaluarlo contra la cartera.")

if not posiciones and not watchlist:
    st.stop()

historicos = obtener_historicos_decision(posiciones, watchlist)
if historicos.empty:
    st.warning("No se pudo obtener histórico de precios en este momento.")
    st.stop()

rf = settings.RISK_FREE_RATE
pesos = {p.ticker: p.peso for p in posiciones if p.peso and p.ticker in historicos.columns}
tenencias = set(pesos)
candidatos = [i.ticker for i in watchlist if i.ticker in historicos.columns]
sin_historia = [i.ticker for i in watchlist if i.ticker not in historicos.columns]
if sin_historia:
    st.caption(f"⚠️ Sin históricos (revisá el ticker o el ADR): {', '.join(sin_historia)}.")

# ==================== MÉTRICAS ====================
st.divider()
st.subheader("Métricas por activo")
st.caption(
    "Ventanas de 1 y 3 años calendario; '—' si el activo no tiene historia suficiente. "
    "La fila CARTERA usa los pesos de hoy, constantes, en los días en que cotizaron todas las tenencias."
)

metricas = metricas_por_activo(historicos, rf=rf)
if pesos:
    cartera = metricas_cartera(historicos[list(pesos)].dropna(), pesos, rf=rf)
    metricas = pd.concat([metricas, pd.DataFrame([cartera], index=["CARTERA"])])
metricas.insert(0, "Rol", ["Cartera" if t == "CARTERA" else ("Tenencia" if t in tenencias else "Candidato") for t in metricas.index])

COLUMNAS_METRICAS = {
    "cagr_1a": "CAGR 1a", "cagr_3a": "CAGR 3a",
    "vol_1a": "Vol 1a", "vol_3a": "Vol 3a",
    "sharpe_1a": "Sharpe 1a", "sharpe_3a": "Sharpe 3a",
    "sortino_1a": "Sortino 1a", "sortino_3a": "Sortino 3a",
    "max_dd_1a": "Max DD 1a", "max_dd_3a": "Max DD 3a",
    "drawdown_actual": "DD actual",
    "ret_1m": "Ret 1m", "ret_3m": "Ret 3m", "ret_6m": "Ret 6m", "mom_12_1": "Mom 12-1",
    "vs_sma50": "vs SMA50", "vs_sma200": "vs SMA200", "rsi_14": "RSI 14",
}
tabla = metricas.rename(columns=COLUMNAS_METRICAS)
NO_PCT = {"Sharpe 1a", "Sharpe 3a", "Sortino 1a", "Sortino 3a", "RSI 14"}
FORMATOS_METRICAS = {c: ("{:.2f}" if c in NO_PCT else "{:.1%}") for c in COLUMNAS_METRICAS.values()}
REGLAS_METRICAS = {
    "CAGR 1a": "signo", "CAGR 3a": "signo", "Vol 1a": "volatilidad", "Vol 3a": "volatilidad",
    "Sharpe 1a": "signo", "Sharpe 3a": "signo", "Sortino 1a": "signo", "Sortino 3a": "signo",
    "Max DD 1a": "drawdown", "Max DD 3a": "drawdown", "DD actual": "drawdown",
    "Ret 1m": "signo", "Ret 3m": "signo", "Ret 6m": "signo", "Mom 12-1": "signo",
    "vs SMA50": "signo", "vs SMA200": "signo", "RSI 14": "rsi",
}
GRUPOS_METRICAS = {
    "📈 Rendimiento": ["CAGR 1a", "CAGR 3a", "Sharpe 1a", "Sharpe 3a", "Sortino 1a", "Sortino 3a"],
    "⚠️ Riesgo": ["Vol 1a", "Vol 3a", "Max DD 1a", "Max DD 3a", "DD actual"],
    "🧭 Momentum y técnicos": ["Ret 1m", "Ret 3m", "Ret 6m", "Mom 12-1", "vs SMA50", "vs SMA200", "RSI 14"],
}
for pestania, columnas in zip(st.tabs(list(GRUPOS_METRICAS)), GRUPOS_METRICAS.values()):
    with pestania:
        st.dataframe(
            semaforos.tabla(tabla[["Rol"] + columnas], FORMATOS_METRICAS, REGLAS_METRICAS), width="stretch"
        )
st.caption(
    f"{semaforos.LEYENDA}. Vol: 🟡 > {semaforos.VOL_MEDIA:.0%}, 🔴 > {semaforos.VOL_ALTA:.0%}. "
    f"Max DD: 🟡 peor que {semaforos.DD_MEDIO:.0%}, 🔴 peor que {semaforos.DD_ALTO:.0%}. "
    f"RSI: 🔴 fuera de {semaforos.RSI_SOBREVENDIDO}–{semaforos.RSI_SOBRECOMPRADO} (sobrevendido / sobrecomprado). "
    "Rendimiento y momentum: verde si es positivo."
)
with st.expander("¿Cómo se calcula cada métrica?"):
    st.markdown(
        """
- **CAGR**: (precio final / inicial)^(1/años) − 1. **Vol**: desvío de retornos diarios × √252.
- **Sharpe**: (CAGR − rf) / Vol. **Sortino**: igual, pero con el desvío de los días negativos.
- **Max DD**: peor caída desde un máximo dentro de la ventana. **DD actual**: hoy vs. máximo de 252 ruedas.
- **Ret 1m/3m/6m**: 21/63/126 ruedas. **Mom 12-1**: de hace 252 a hace 21 ruedas (saltea el último mes).
- **vs SMA**: precio / promedio de N ruedas − 1. **RSI 14**: promedio de subas / bajas de 14 ruedas.
"""
    )

# ==================== RANKING ====================
st.divider()
st.subheader("Ranking de candidatos")
if not candidatos:
    st.info("Agregá candidatos con históricos a la watchlist para rankearlos.")
    st.stop()
if not pesos:
    st.info("Necesitás al menos una tenencia con históricos para medir el impacto de un candidato.")
    st.stop()

peso_objetivo = st.slider(
    "Peso objetivo del candidato", min_value=1, max_value=50, value=int(PESO_OBJETIVO_DEFAULT * 100),
    format="%d%%", help="La cartera actual se escala a (1 − peso) y el candidato entra con ese peso.",
) / 100

ranking = rankear_candidatos(historicos, pesos, candidatos, peso_objetivo, rf=rf)

valor_cartera = resumen_cartera(posiciones)["valor_actual_total"] if posiciones else None
items = {i.ticker: i for i in watchlist}
precios = {t: obtener_precio_unidad(items[t]) for t in ranking.index}
ranking["precio_unidad"] = [precios[t] for t in ranking.index]
ranking["peso_1_unidad"] = [peso_de_una_unidad(precios[t], valor_cartera) for t in ranking.index]
ranking["unidades"] = [unidades_para_peso(precios[t], valor_cartera, peso_objetivo) for t in ranking.index]

for t, peso_unidad in ranking["peso_1_unidad"].items():
    if peso_unidad is not None and peso_unidad > peso_objetivo:
        st.error(
            f"**{t}**: 1 unidad ({formato_moneda(precios[t])}) ya es el {formato_pct(peso_unidad)} de la cartera, "
            f"más que el {formato_pct(peso_objetivo)} objetivo. No podés llegar a ese peso sin pasarte."
        )

st.caption(
    "Δ = cartera con el candidato − cartera actual, en los días que cotizaron todos. Ordenado por Δ Sharpe 3a. "
    "Δ Vol negativo = menos volátil; Δ Max DD positivo = caída máxima más chica."
)
COLUMNAS_RANKING = {
    "delta_vol_1a": "Δ Vol 1a", "delta_sharpe_1a": "Δ Sharpe 1a", "delta_max_dd_1a": "Δ Max DD 1a",
    "delta_vol_3a": "Δ Vol 3a", "delta_sharpe_3a": "Δ Sharpe 3a", "delta_max_dd_3a": "Δ Max DD 3a",
    "corr_cartera": "Corr. cartera", "mas_correlacionada": "Más correlacionada con",
    "corr_mas_correlacionada": "Corr. máx.", "dias": "Ruedas", "precio_unidad": "Precio 1 unidad",
    "peso_1_unidad": "Peso 1 unidad", "unidades": "Unidades p/ objetivo", "error": "Aviso",
}
tabla_ranking = ranking.rename(columns=COLUMNAS_RANKING)
REGLAS_RANKING = {
    "Δ Vol 1a": "signo_inverso", "Δ Vol 3a": "signo_inverso",
    "Δ Sharpe 1a": "signo", "Δ Sharpe 3a": "signo",
    "Δ Max DD 1a": "signo", "Δ Max DD 3a": "signo",
    "Corr. cartera": "correlacion", "Corr. máx.": "correlacion",
}
tabla_ranking.insert(0, "Señal", semaforos.columna_senal(tabla_ranking, {"Δ Sharpe 3a": "signo", "Δ Vol 3a": "signo_inverso"}))
st.dataframe(
    semaforos.tabla(
        tabla_ranking,
        {
            "Δ Vol 1a": "{:+.2%}", "Δ Vol 3a": "{:+.2%}",
            "Δ Sharpe 1a": "{:+.2f}", "Δ Sharpe 3a": "{:+.2f}",
            "Δ Max DD 1a": "{:+.2%}", "Δ Max DD 3a": "{:+.2%}",
            "Corr. cartera": "{:.2f}", "Corr. máx.": "{:.2f}",
            "Precio 1 unidad": "$ {:,.2f}", "Peso 1 unidad": "{:.1%}",
            "Ruedas": "{:,.0f}", "Unidades p/ objetivo": "{:,.0f}",
        },
        REGLAS_RANKING,
    ),
    width="stretch",
)
st.caption(
    f"{semaforos.LEYENDA}. Verde = el candidato mejora la cartera en esa métrica (Δ Vol: baja; "
    f"Δ Sharpe y Δ Max DD: sube). Señal = peor de Δ Sharpe 3a y Δ Vol 3a. Correlación: "
    f"🟡 > {semaforos.CORR_MEDIA}, 🔴 > {semaforos.CORR_ALTA} (diversifica poco)."
)

# ==================== DETALLE ====================
st.markdown("##### Antes / después")
elegido = st.selectbox("Candidato", list(ranking.index))
detalle = evaluar_candidato(historicos, pesos, elegido, peso_objetivo, rf=rf)
if detalle.get("error"):
    st.info(detalle["error"])
else:
    claves = [k for k in COLUMNAS_METRICAS if k.endswith(("_1a", "_3a"))]
    comparacion = pd.DataFrame(
        {
            "Actual": [detalle["antes"].get(k) for k in claves],
            f"Con {elegido} al {peso_objetivo:.0%}": [detalle["despues"].get(k) for k in claves],
        },
        index=[COLUMNAS_METRICAS[k] for k in claves],
    )
    comparacion["Δ"] = comparacion.iloc[:, 1] - comparacion.iloc[:, 0]
    estilo = comparacion.style
    for fila in comparacion.index:
        formato = "{:.2f}" if fila in NO_PCT else "{:.2%}"
        estilo = estilo.format(formato, subset=pd.IndexSlice[[fila], comparacion.columns[:2]], na_rep="—")
        estilo = estilo.format("{:+" + formato[2:], subset=pd.IndexSlice[[fila], ["Δ"]], na_rep="—")
    reglas_delta = {f: ("signo_inverso" if f.startswith("Vol") else "signo") for f in comparacion.index}
    st.dataframe(semaforos.estilar_filas(estilo, reglas_delta, columnas=["Δ"]), width="stretch")
    corr = detalle["corr_posiciones"]
    if not corr.empty:
        st.caption("Correlación de retornos diarios con cada tenencia:")
        st.bar_chart(corr.sort_values(ascending=False))
