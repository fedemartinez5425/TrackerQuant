"""
Motor de insights: reglas financieras determinísticas (no IA, no caja
negra) que traducen las métricas ya calculadas (volatilidad, VaR/CVaR,
correlación, beta, concentración) en un diagnóstico + qué mirar para
research posterior. Pensado como punto de partida para investigar en
otra herramienta (una IA, un screener), no como asesoramiento financiero
personalizado -- el reporte lo dice explícitamente.

Todos los umbrales son los mismos que ya usa el semáforo de riesgo
(core/risk/volatility.py) para que el diagnóstico sea consistente con lo
que el usuario ve en el resto de la app.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Insight:
    severidad: str  # "alto" | "medio" | "bajo" | "info"
    categoria: str
    diagnostico: str
    recomendacion: str


ICONO_SEVERIDAD = {"alto": "🔴", "medio": "🟡", "bajo": "🟢", "info": "ℹ️"}


def _evaluar_volatilidad(vol: float | None) -> Insight | None:
    if vol is None:
        return None
    if vol > 0.40:
        return Insight(
            "alto", "Volatilidad",
            f"Volatilidad anualizada muy alta ({vol:.1%}, umbral de alerta: 40%).",
            "Priorizar research en empresas de alta capitalización, flujo de caja estable y "
            "sectores defensivos (consumo masivo, salud, utilities) para bajar la volatilidad "
            "total sin salir del mercado. Evitar sumar más nombres de alta beta o small caps.",
        )
    if vol > 0.25:
        return Insight(
            "medio", "Volatilidad",
            f"Volatilidad anualizada moderada-alta ({vol:.1%}).",
            "Vigilar de cerca las posiciones más volátiles; no es urgente reducir, pero conviene "
            "evaluar si el nivel de riesgo sigue alineado con tu horizonte de inversión.",
        )
    return Insight("bajo", "Volatilidad", f"Volatilidad anualizada controlada ({vol:.1%}).", "Nivel razonable — no requiere acción.")


def _evaluar_concentracion(concentracion_top2: float | None, contribucion) -> Insight | None:
    if concentracion_top2 is None:
        return None
    top2_nombres = ", ".join(contribucion.sort_values(ascending=False).index[:2]) if contribucion is not None and len(contribucion) >= 2 else ""
    if concentracion_top2 > 0.75:
        return Insight(
            "alto", "Concentración",
            f"El {concentracion_top2:.0%} del riesgo total viene de solo 2 posiciones" + (f" ({top2_nombres})" if top2_nombres else "") + ".",
            f"Considerar reducir el tamaño de {top2_nombres or 'tus posiciones más grandes'} y "
            "redistribuir hacia activos con baja correlación frente a ellas, para que ningún "
            "evento idiosincrático de una sola empresa/sector pese tanto en el resultado total.",
        )
    if concentracion_top2 > 0.55:
        return Insight(
            "medio", "Concentración",
            f"El {concentracion_top2:.0%} del riesgo total se concentra en 2 posiciones" + (f" ({top2_nombres})" if top2_nombres else "") + ".",
            "Concentración moderada — hay margen para diversificar un poco más si el objetivo es bajar riesgo idiosincrático.",
        )
    return Insight("bajo", "Concentración", "El riesgo está razonablemente repartido entre posiciones.", "Nivel de diversificación adecuado.")


def _evaluar_correlacion(corr: float | None) -> Insight | None:
    if corr is None:
        return None
    if corr > 0.7:
        return Insight(
            "alto", "Correlación",
            f"Correlación promedio ponderada alta ({corr:.2f}) — tus posiciones tienden a moverse juntas.",
            "Buscar activos con correlación histórica baja o negativa frente al resto de la cartera: "
            "otros sectores, otra geografía, o activos con drivers distintos (ej. si la cartera es "
            "tech-heavy, mirar consumo defensivo o salud; si es todo Argentina, mirar diversificar moneda/geografía).",
        )
    if corr > 0.4:
        return Insight(
            "medio", "Correlación",
            f"Correlación promedio ponderada moderada ({corr:.2f}).",
            "Diversificación aceptable, pero hay margen para bajar la correlación entre tus posiciones más grandes.",
        )
    return Insight("bajo", "Correlación", f"Correlación promedio ponderada baja ({corr:.2f}) — buena diversificación real.", "Mantener el criterio actual de selección.")


def _evaluar_beta(beta: float | None, benchmark: str) -> Insight | None:
    if beta is None:
        return None
    if beta > 1.2:
        return Insight(
            "alto", "Beta / Sensibilidad al mercado",
            f"Beta de {beta:.2f} vs. {benchmark}: la cartera amplifica los movimientos del mercado.",
            "Si el objetivo es bajar riesgo sistemático, priorizar research en acciones de beta bajo "
            "(<0.8) — históricamente sectores no cíclicos (utilities, consumo defensivo, salud) o "
            "empresas maduras con ingresos más predecibles.",
        )
    if beta < 0.7:
        return Insight(
            "info", "Beta / Sensibilidad al mercado",
            f"Beta de {beta:.2f} vs. {benchmark}: cartera defensiva, poco sensible al mercado.",
            "Coherente si buscás estabilidad; tené en cuenta que también vas a captar menos si el mercado sube fuerte.",
        )
    return Insight("bajo", "Beta / Sensibilidad al mercado", f"Beta de {beta:.2f} vs. {benchmark}: en línea con el mercado.", "Nivel razonable.")


def _evaluar_cola_perdidas(var_95: float | None, cvar_95: float | None) -> Insight | None:
    if var_95 is None or cvar_95 is None or var_95 == 0:
        return None
    ratio = cvar_95 / var_95
    if ratio > 1.5:
        return Insight(
            "medio", "Riesgo de cola",
            f"El CVaR (Expected Shortfall) es {ratio:.1f}x el VaR — cuando hay un mal día, suele ser bastante peor que el límite típico.",
            "Revisar si hay posiciones con historial de saltos abruptos (small caps, alta volatilidad "
            "idiosincrática, baja liquidez) que expliquen esa cola pesada, y considerar acotarlas.",
        )
    return None


def _evaluar_contribucion_desproporcionada(posiciones, contribucion) -> list[Insight]:
    """Detecta posiciones que aportan mucho más riesgo del que su tamaño sugiere."""
    insights = []
    if contribucion is None or contribucion.empty:
        return insights
    contrib_dict = contribucion.to_dict()
    for p in posiciones:
        if not p.peso or p.ticker not in contrib_dict:
            continue
        contrib_pct = contrib_dict[p.ticker]
        if contrib_pct > p.peso * 1.5 and contrib_pct > 0.15:
            insights.append(
                Insight(
                    "medio", "Contribución desproporcionada",
                    f"{p.ticker} pesa {p.peso:.1%} de la cartera pero aporta {contrib_pct:.1%} del riesgo total.",
                    f"Candidato a revisar/recortar: {p.ticker} está aportando más riesgo del que su "
                    "tamaño sugiere (suele pasar con activos muy volátiles o muy correlacionados con el resto).",
                )
            )
    return insights


def generar_insights(riesgo: dict, posiciones: list, benchmark: str) -> list[Insight]:
    """Corre todas las reglas y devuelve la lista de insights disparados
    (incluye también los de severidad 'bajo'/'info', para mostrar
    fortalezas y no solo alertas)."""
    insights = []
    for fn, args in [
        (_evaluar_volatilidad, (riesgo.get("volatilidad_anualizada"),)),
        (_evaluar_concentracion, (riesgo.get("concentracion_top2"), riesgo.get("contribucion_riesgo"))),
        (_evaluar_correlacion, (riesgo.get("correlacion_ponderada"),)),
        (_evaluar_beta, (riesgo.get("beta_cartera"), benchmark)),
        (_evaluar_cola_perdidas, (riesgo.get("var_95_pct"), riesgo.get("cvar_95_pct"))),
    ]:
        resultado = fn(*args)
        if resultado:
            insights.append(resultado)
    insights.extend(_evaluar_contribucion_desproporcionada(posiciones, riesgo.get("contribucion_riesgo")))
    return insights


def generar_reporte_markdown(riesgo: dict, posiciones: list, resumen_cartera: dict, benchmark: str) -> str:
    """Arma el reporte completo en Markdown -- pensado para copiar y pegar
    en una IA externa como punto de partida para investigar acciones."""
    insights = generar_insights(riesgo, posiciones, benchmark)
    alertas = [i for i in insights if i.severidad == "alto"]
    a_vigilar = [i for i in insights if i.severidad == "medio"]
    fortalezas = [i for i in insights if i.severidad in ("bajo", "info")]

    lineas = [
        f"# Reporte de Riesgo de Cartera — {date.today().isoformat()}",
        "",
        f"**Semáforo general:** {riesgo.get('semaforo', '—')}  ",
        f"**Valor de cartera:** $ {resumen_cartera.get('valor_actual_total', 0):,.2f}  ",
        f"**Posiciones:** {resumen_cartera.get('cantidad_posiciones', 0)}  ",
        f"**Volatilidad anualizada:** {_pct(riesgo.get('volatilidad_anualizada'))}  ",
        f"**VaR histórico 95%:** {_pct(riesgo.get('var_95_pct'))} · **CVaR 95%:** {_pct(riesgo.get('cvar_95_pct'))}  ",
        f"**Beta vs. {benchmark}:** {_num(riesgo.get('beta_cartera'))} · **Correlación promedio:** {_num(riesgo.get('correlacion_ponderada'))}",
        "",
        "---",
        "",
    ]

    if alertas:
        lineas.append("## 🔴 Alertas")
        for i in alertas:
            lineas += [f"**{i.categoria}** — {i.diagnostico}", f"> {i.recomendacion}", ""]

    if a_vigilar:
        lineas.append("## 🟡 A vigilar")
        for i in a_vigilar:
            lineas += [f"**{i.categoria}** — {i.diagnostico}", f"> {i.recomendacion}", ""]

    if fortalezas:
        lineas.append("## 🟢 En línea / fortalezas")
        for i in fortalezas:
            lineas += [f"**{i.categoria}** — {i.diagnostico}", ""]

    lineas.append("## 🔎 Qué priorizar en tu próxima research")
    criterios = _sintetizar_criterios_busqueda(insights)
    if criterios:
        lineas.append(criterios)
    else:
        lineas.append("Sin señales de alerta relevantes — no hay un sesgo particular que priorizar por ahora.")
    lineas.append("")

    candidatos = [i for i in insights if i.categoria == "Contribución desproporcionada"]
    if candidatos:
        lineas.append("## ✂️ Candidatos a revisar/reducir")
        for i in candidatos:
            lineas.append(f"- {i.diagnostico}")
        lineas.append("")

    lineas += [
        "---",
        "_Este reporte es 100% generado por reglas cuantitativas a partir de tus propios datos "
        "(no es un modelo de IA ni asesoramiento financiero personalizado). Pensado como punto de "
        "partida para investigar por tu cuenta o con otra herramienta — no como una recomendación de compra/venta._",
    ]
    return "\n".join(lineas)


def _sintetizar_criterios_busqueda(insights: list[Insight]) -> str:
    categorias_alerta = {i.categoria for i in insights if i.severidad in ("alto", "medio")}
    criterios = []
    if "Volatilidad" in categorias_alerta:
        criterios.append("empresas de alta capitalización y flujo de caja estable")
    if "Beta / Sensibilidad al mercado" in categorias_alerta:
        criterios.append("beta bajo (<0.8), sectores no cíclicos (utilities, consumo defensivo, salud)")
    if "Correlación" in categorias_alerta:
        criterios.append("activos con correlación histórica baja o negativa frente a tu cartera actual")
    if "Concentración" in categorias_alerta:
        criterios.append("diversificar fuera de tus posiciones más grandes actuales")
    if "Riesgo de cola" in categorias_alerta:
        criterios.append("evitar sumar más exposición a activos de alta volatilidad idiosincrática")
    if not criterios:
        return ""
    return "Dado el diagnóstico anterior, para tu próxima research priorizá: " + "; ".join(criterios) + "."


def _pct(v: float | None) -> str:
    return f"{v:.2%}" if v is not None else "—"


def _num(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "—"
