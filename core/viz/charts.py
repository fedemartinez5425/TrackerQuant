"""
Constructores de gráficos Plotly reutilizables, todos con la misma
identidad visual (core/viz/palette.py). Ninguna página arma un gráfico
"a mano" -- todas llaman a estas funciones, así los colores y el estilo
son consistentes en toda la app (y si mañana cambia la paleta, se cambia
en un solo lugar).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from core.viz import palette as p


def donut_exposicion(pesos: dict[str, float], titulo: str = "") -> go.Figure:
    """Donut de exposición por posición, con etiqueta de % en cada segmento."""
    items = sorted(pesos.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    colores = (p.CHART_SEQUENCE * ((len(labels) // len(p.CHART_SEQUENCE)) + 1))[: len(labels)]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.62,
                marker=dict(colors=colores, line=dict(color=p.BG_DARK, width=2)),
                textinfo="label+percent",
                textfont=dict(family=p.FONT_FAMILY, color=p.TEXT_PRIMARY, size=12),
                hovertemplate="%{label}: %{percent}<extra></extra>",
                sort=False,
            )
        ]
    )
    total_pct = sum(values)
    fig.add_annotation(
        text=f"<b>{total_pct:.0%}</b><br><span style='font-size:11px;color={p.TEXT_SECONDARY}'>asignado</span>",
        showarrow=False,
        font=dict(family=p.FONT_FAMILY_DISPLAY, size=20, color=p.TEXT_PRIMARY),
    )
    fig.update_layout(**p.plotly_layout_defaults(altura=320), showlegend=False, title=titulo)
    return fig


def barras_horizontales(
    categorias: list[str], valores: list[float], titulo: str = "", formato_pct: bool = True, invertir_color: bool = False
) -> go.Figure:
    """Barras horizontales con degradado y etiqueta de dato al final de cada barra
    (ej: contribución al riesgo por activo). Ordenadas de mayor a menor."""
    orden = sorted(zip(categorias, valores), key=lambda t: abs(t[1]), reverse=True)
    cats = [c for c, _ in orden]
    vals = [v for _, v in orden]

    max_abs = max((abs(v) for v in vals), default=1) or 1
    colores = []
    for v in vals:
        intensidad = 0.35 + 0.65 * (abs(v) / max_abs)
        colores.append(p.DANGER if (v < 0 and invertir_color) else _mezclar(p.ACCENT_DIM, p.ACCENT, intensidad))

    textos = [f"{v:.1%}" if formato_pct else f"{v:,.2f}" for v in vals]

    fig = go.Figure(
        go.Bar(
            x=vals,
            y=cats,
            orientation="h",
            marker=dict(color=colores, line=dict(width=0)),
            text=textos,
            textposition="outside",
            textfont=dict(family=p.FONT_FAMILY_MONO, color=p.TEXT_PRIMARY, size=12),
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    fig.update_layout(**p.plotly_layout_defaults(altura=max(220, 42 * len(cats))), title=titulo)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(showticklabels=False, showgrid=False, zeroline=False)
    return fig


def area_evolucion(serie: pd.Series, titulo: str = "", nombre: str = "Cartera") -> go.Figure:
    """Línea con relleno degradado -- evolución de índice/VaR/valor en el tiempo,
    con el último valor remarcado como etiqueta (como el gráfico de referencia)."""
    fig = go.Figure(
        go.Scatter(
            x=serie.index,
            y=serie.values,
            mode="lines",
            line=dict(color=p.ACCENT, width=2.2),
            fill="tozeroy",
            fillgradient=dict(
                type="vertical",
                colorscale=[[0, "rgba(0,232,168,0.0)"], [1, "rgba(0,232,168,0.28)"]],
            ),
            name=nombre,
            hovertemplate="%{x|%d %b %Y}: %{y:.2f}<extra></extra>",
        )
    )
    ultimo_x, ultimo_y = serie.index[-1], serie.values[-1]
    fig.add_annotation(
        x=ultimo_x, y=ultimo_y, text=f"<b>{ultimo_y:,.2f}</b>", showarrow=True, arrowhead=0,
        ax=30, ay=-20, font=dict(family=p.FONT_FAMILY_MONO, color=p.ACCENT, size=13),
        bgcolor=p.BG_PANEL_LIGHT, bordercolor=p.ACCENT, borderwidth=1, borderpad=4,
    )
    fig.update_layout(**p.plotly_layout_defaults(altura=300), title=titulo, showlegend=False)
    return fig


def histograma_retornos(retornos: pd.Series, titulo: str = "") -> go.Figure:
    """Distribución de retornos diarios, con la cola izquierda (pérdidas) resaltada."""
    fig = go.Figure(
        go.Histogram(
            x=retornos * 100,
            nbinsx=40,
            marker=dict(color=p.ACCENT_DIM, line=dict(color=p.ACCENT, width=0.6)),
            hovertemplate="Retorno: %{x:.2f}%<br>Días: %{y}<extra></extra>",
        )
    )
    fig.update_layout(**p.plotly_layout_defaults(altura=280), title=titulo, bargap=0.05)
    fig.update_xaxes(title="Retorno diario (%)")
    fig.update_yaxes(title="Frecuencia (días)")
    return fig


def heatmap_correlacion(matriz: pd.DataFrame, titulo: str = "") -> go.Figure:
    fig = go.Figure(
        go.Heatmap(
            z=matriz.values,
            x=matriz.columns,
            y=matriz.index,
            colorscale=p.CHART_DIVERGING,
            zmin=-1,
            zmax=1,
            text=matriz.values,
            texttemplate="%{text:.2f}",
            textfont=dict(family=p.FONT_FAMILY_MONO, size=11),
            hovertemplate="%{y} × %{x}: %{z:.2f}<extra></extra>",
            colorbar=dict(outlinewidth=0, tickfont=dict(color=p.TEXT_SECONDARY)),
        )
    )
    fig.update_layout(**p.plotly_layout_defaults(altura=380), title=titulo)
    return fig


def barras_escenarios_estres(escenarios: list[dict], titulo: str = "") -> go.Figure:
    labels = [e["Escenario"] for e in escenarios]
    valores = [e["Impacto Estimado $"] or 0 for e in escenarios]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=valores,
            marker=dict(color=p.DANGER),
            text=[f"$ {v:,.0f}" for v in valores],
            textposition="outside",
            textfont=dict(family=p.FONT_FAMILY_MONO, color=p.TEXT_PRIMARY, size=11),
            hovertemplate="%{x}: $ %{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(**p.plotly_layout_defaults(altura=300), title=titulo)
    fig.update_yaxes(showgrid=True)
    return fig


def linea_multi(df: pd.DataFrame, titulo: str = "") -> go.Figure:
    """Múltiples series normalizadas (ej. históricos base 100), con la paleta
    categórica de la marca en vez de los colores default de Plotly."""
    fig = go.Figure()
    colores = (p.CHART_SEQUENCE * ((len(df.columns) // len(p.CHART_SEQUENCE)) + 1))[: len(df.columns)]
    for col, color in zip(df.columns, colores):
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df[col], mode="lines", name=col,
                line=dict(color=color, width=2),
                hovertemplate=f"{col}: " + "%{y:.1f}<extra></extra>",
            )
        )
    fig.update_layout(**p.plotly_layout_defaults(altura=340), title=titulo)
    return fig


def cono_forecast(
    historico: pd.Series, cono_df: pd.DataFrame, titulo: str = "", nombre_historico: str = "Realizado",
    dias_historico_mostrar: int = 60,
) -> go.Figure:
    """Cono de incertidumbre: histórico reciente (días negativos) + banda
    95%/68% hacia adelante (días positivos), sobre un único eje de 'días
    relativos a hoy' -- como en un dashboard de forecasting profesional."""
    historico_reciente = historico.dropna().tail(dias_historico_mostrar)
    x_historico = list(range(-len(historico_reciente) + 1, 1))  # ... -2, -1, 0 (hoy)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_historico, y=historico_reciente.values, mode="lines", name=nombre_historico,
            line=dict(color=p.ACCENT, width=2),
            hovertemplate="Día %{x}: %{y:.2f}<extra></extra>",
        )
    )

    ultimo_valor_historico = historico_reciente.iloc[-1]
    x_forecast = list(cono_df.index)
    fig.add_trace(go.Scatter(x=[0] + x_forecast, y=[ultimo_valor_historico] + list(cono_df["banda_95_sup"]), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(
        go.Scatter(
            x=[0] + x_forecast, y=[ultimo_valor_historico] + list(cono_df["banda_95_inf"]),
            mode="lines", line=dict(width=0), fill="tonexty",
            fillcolor="rgba(0,232,168,0.10)", name="Banda 95%",
            hovertemplate="%{y:.2f}<extra>Banda 95%%</extra>",
        )
    )
    fig.add_trace(go.Scatter(x=[0] + x_forecast, y=[ultimo_valor_historico] + list(cono_df["banda_68_sup"]), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(
        go.Scatter(
            x=[0] + x_forecast, y=[ultimo_valor_historico] + list(cono_df["banda_68_inf"]),
            mode="lines", line=dict(width=0), fill="tonexty",
            fillcolor="rgba(0,232,168,0.22)", name="Banda 68%",
            hovertemplate="%{y:.2f}<extra>Banda 68%%</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[0] + x_forecast, y=[ultimo_valor_historico] + list(cono_df["esperado"]),
            mode="lines", name="Esperado", line=dict(color=p.TEXT_PRIMARY, width=1.6, dash="dash"),
            hovertemplate="Día +%{x}: %{y:.2f}<extra></extra>",
        )
    )

    fig.update_layout(**p.plotly_layout_defaults(altura=360), title=titulo)
    fig.update_xaxes(title="Días relativos a hoy (0 = hoy)")
    fig.add_vline(x=0, line_dash="dot", line_color=p.TEXT_MUTED)
    return fig


def linea_volatilidad_forecast(
    vol_realizada: pd.Series, vol_condicional: pd.Series, forecast_path: pd.Series, titulo: str = "",
    dias_historico_mostrar: int = 120,
) -> go.Figure:
    """Volatilidad realizada (móvil) vs. condicional (GARCH) históricas,
    más el forecast hacia adelante en días relativos a hoy."""
    vol_realizada_r = vol_realizada.dropna().tail(dias_historico_mostrar)
    vol_condicional_r = vol_condicional.reindex(vol_realizada_r.index).dropna()

    x_hist = list(range(-len(vol_realizada_r) + 1, 1))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=x_hist, y=vol_realizada_r.values, mode="lines", name="Realizada (móvil 21d)",
                   line=dict(color=p.TEXT_SECONDARY, width=1.5), hovertemplate="Día %{x}: %{y:.1%}<extra></extra>")
    )
    x_cond = list(range(-len(vol_condicional_r) + 1, 1))
    fig.add_trace(
        go.Scatter(x=x_cond, y=vol_condicional_r.values, mode="lines", name="Condicional (GARCH)",
                   line=dict(color=p.ACCENT, width=2), hovertemplate="Día %{x}: %{y:.1%}<extra></extra>")
    )
    x_forecast = list(forecast_path.index)
    ultimo_valor = vol_condicional_r.iloc[-1] if not vol_condicional_r.empty else vol_realizada_r.iloc[-1]
    fig.add_trace(
        go.Scatter(
            x=[0] + x_forecast, y=[ultimo_valor] + list(forecast_path.values), mode="lines+markers",
            name="Forecast", line=dict(color=p.WARNING, width=2, dash="dash"),
            marker=dict(size=5), hovertemplate="Día +%{x}: %{y:.1%}<extra></extra>",
        )
    )
    fig.update_layout(**p.plotly_layout_defaults(altura=340), title=titulo)
    fig.update_yaxes(tickformat=".0%")
    fig.update_xaxes(title="Días relativos a hoy (0 = hoy)")
    fig.add_vline(x=0, line_dash="dot", line_color=p.TEXT_MUTED)
    return fig


def _mezclar(color_a: str, color_b: str, t: float) -> str:
    """Interpola linealmente entre dos colores hex (t=0 -> color_a, t=1 -> color_b)."""
    a = tuple(int(color_a.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    b = tuple(int(color_b.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    mezcla = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return f"rgb({mezcla[0]},{mezcla[1]},{mezcla[2]})"
