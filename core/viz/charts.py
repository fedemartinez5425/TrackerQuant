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

from core.viz import formato
from core.viz import palette as p


def donut_exposicion(pesos: dict[str, float], titulo: str = "", umbral_alerta: float | None = None) -> go.Figure:
    """Donut de exposición por posición, con etiqueta de % en cada segmento.
    Las posiciones que superan `umbral_alerta` van en rojo, y el centro
    muestra el dato relevante: la posición más grande."""
    items = sorted(pesos.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    colores = (p.CHART_SEQUENCE * ((len(labels) // len(p.CHART_SEQUENCE)) + 1))[: len(labels)]
    if umbral_alerta is not None:
        colores = [p.DANGER if v > umbral_alerta else c for c, v in zip(colores, values)]

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
    if labels:
        mayor_color = p.DANGER if umbral_alerta is not None and values[0] > umbral_alerta else p.TEXT_PRIMARY
        fig.add_annotation(
            text=(
                f"<b>{formato.pct(values[0], 0)}</b><br>"
                f"<span style='font-size:11px;color={p.TEXT_SECONDARY}'>mayor: {labels[0]}</span>"
            ),
            showarrow=False,
            font=dict(family=p.FONT_FAMILY_DISPLAY, size=20, color=mayor_color),
        )
    fig.update_layout(**p.plotly_layout_defaults(altura=320), showlegend=False, title=titulo)
    return fig


def barras_horizontales(
    categorias: list[str], valores: list[float], titulo: str = "", formato_pct: bool = True, invertir_color: bool = False,
    resaltar: set[str] | None = None, referencia: dict[str, float] | None = None, nombre_referencia: str = "peso",
) -> go.Figure:
    """Barras horizontales con degradado y etiqueta de dato al final de cada barra
    (ej: contribución al riesgo por activo). Ordenadas de mayor a menor.
    `resaltar`: categorías en rojo (alerta). `referencia`: un valor de
    comparación por categoría (ej. el peso), que se agrega a la etiqueta."""
    orden = sorted(zip(categorias, valores), key=lambda t: abs(t[1]), reverse=True)
    cats = [c for c, _ in orden]
    vals = [v for _, v in orden]

    max_abs = max((abs(v) for v in vals), default=1) or 1
    colores = []
    for v in vals:
        intensidad = 0.35 + 0.65 * (abs(v) / max_abs)
        colores.append(p.DANGER if (v < 0 and invertir_color) else _mezclar(p.ACCENT_DIM, p.ACCENT, intensidad))
    if resaltar:
        colores = [p.DANGER if c in resaltar else col for c, col in zip(cats, colores)]

    textos = [formato.pct(v, 1) if formato_pct else formato.fmt(v, ",.2f") for v in vals]
    if referencia:
        textos = [
            f"{t}  <span style='color:{p.TEXT_SECONDARY}'>({nombre_referencia} {formato.pct(referencia[c], 0)})</span>"
            if referencia.get(c) is not None else t
            for c, t in zip(cats, textos)
        ]

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
    # Lugar a la derecha para que la etiqueta de la barra más larga no se corte.
    tope = max((abs(v) for v in vals), default=1) or 1
    piso = min(0, min(vals, default=0))
    fig.update_xaxes(showticklabels=False, showgrid=False, zeroline=False, range=[piso * 1.4, tope * 1.6])
    return fig


def area_evolucion(serie: pd.Series, titulo: str = "", nombre: str = "Cartera", marcar_maximo: bool = True) -> go.Figure:
    """Línea con relleno degradado -- evolución de índice/VaR/valor en el tiempo,
    con el último valor remarcado como etiqueta. Con `marcar_maximo`, marca el
    máximo y la caída actual desde ese máximo (en rojo si es fuerte)."""
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
            hovertemplate="%{x|%d/%m/%Y}: %{y:,.2f}<extra></extra>",
        )
    )
    ultimo_x, ultimo_y = serie.index[-1], serie.values[-1]
    texto_ultimo = f"<b>{formato.fmt(ultimo_y, ',.2f')}</b>"
    color_ultimo = p.ACCENT
    if marcar_maximo and len(serie) > 1:
        max_x, max_y = serie.idxmax(), serie.max()
        caida = ultimo_y / max_y - 1 if max_y else 0
        if max_x != ultimo_x:
            fig.add_trace(go.Scatter(
                x=[max_x], y=[max_y], mode="markers", marker=dict(color=p.TEXT_PRIMARY, size=7),
                hovertemplate="Máximo %{x|%d/%m/%Y}: %{y:,.2f}<extra></extra>", showlegend=False,
            ))
            fig.add_annotation(
                x=max_x, y=max_y, text=f"máx. {formato.fmt(max_y, ',.1f')}", showarrow=False, yshift=14,
                font=dict(family=p.FONT_FAMILY_MONO, color=p.TEXT_SECONDARY, size=11),
            )
        if caida < -0.005:
            texto_ultimo += f"<br>{formato.pct(caida, 1)} desde el máx."
            if caida <= -0.10:
                color_ultimo = p.DANGER
    fig.add_annotation(
        x=ultimo_x, y=ultimo_y, text=texto_ultimo, showarrow=True, arrowhead=0,
        ax=-10, ay=-34, xanchor="right", font=dict(family=p.FONT_FAMILY_MONO, color=color_ultimo, size=12),
        bgcolor=p.BG_PANEL_LIGHT, bordercolor=color_ultimo, borderwidth=1, borderpad=4, align="right",
    )
    fig.update_layout(**p.plotly_layout_defaults(altura=300), title=titulo, showlegend=False)
    fig.update_xaxes(tickformat="%m/%Y")  # sin nombres de mes en inglés
    return fig


def histograma_retornos(retornos: pd.Series, titulo: str = "", var_pct: float | None = None) -> go.Figure:
    """Distribución de retornos diarios. Con `var_pct` (VaR 95%, negativo),
    los días peores que el VaR van en rojo y se marca el umbral."""
    x = retornos * 100
    ancho = (x.max() - x.min()) / 40 if len(x) > 1 and x.max() > x.min() else 0.25
    bins = dict(start=float(x.min()), end=float(x.max()) + ancho, size=ancho)
    hover = "Retorno: %{x:.2f} %<br>Días: %{y}<extra></extra>"
    fig = go.Figure()
    if var_pct is not None:
        corte = var_pct * 100
        fig.add_trace(go.Histogram(
            x=x[x <= corte], xbins=bins, name="Peores 5 % de los días",
            marker=dict(color=p.DANGER, line=dict(color=p.DANGER, width=0.6)), hovertemplate=hover,
        ))
        fig.add_trace(go.Histogram(
            x=x[x > corte], xbins=bins, name="Resto",
            marker=dict(color=p.ACCENT_DIM, line=dict(color=p.ACCENT, width=0.6)), hovertemplate=hover,
        ))
        fig.add_vline(
            x=corte, line_dash="dash", line_color=p.DANGER,
            annotation_text=f"VaR 95 %: {formato.fmt(corte, '.2f')} %", annotation_position="top left",
            annotation_font=dict(family=p.FONT_FAMILY_MONO, color=p.DANGER, size=11),
        )
    else:
        fig.add_trace(go.Histogram(
            x=x, xbins=bins, marker=dict(color=p.ACCENT_DIM, line=dict(color=p.ACCENT, width=0.6)), hovertemplate=hover,
        ))
    fig.update_layout(
        **p.plotly_layout_defaults(altura=280), title=titulo, bargap=0.05, barmode="overlay", showlegend=False,
    )
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
            text=[formato.moneda(v, decimales=0) for v in valores],
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
        serie = df[col].dropna()
        if not serie.empty:  # etiqueta de dato al final de cada línea
            fig.add_annotation(
                x=serie.index[-1], y=serie.iloc[-1], text=f"{col} {formato.fmt(serie.iloc[-1], '.0f')}",
                showarrow=False, xanchor="left", xshift=6,
                font=dict(family=p.FONT_FAMILY_MONO, color=color, size=11),
            )
    fig.update_layout(**p.plotly_layout_defaults(altura=340), title=titulo)
    fig.update_layout(margin=dict(l=10, r=90, t=40, b=10))
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


def valor_vs_aportes(
    valor: pd.Series, aportes: pd.Series, operaciones: pd.DataFrame | None = None, moneda: str = "ARS", titulo: str = ""
) -> go.Figure:
    """Valor real de la cartera vs. la plata puesta (escalón), con las compras
    (▲) y ventas (▼) marcadas sobre la línea de valor. La distancia entre las
    dos líneas es la ganancia o pérdida acumulada."""
    simbolo = "US$" if moneda == "USD" else "$"
    decimales = ",.0f" if moneda == "ARS" else ",.2f"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=aportes.index, y=aportes.values, mode="lines", name="Plata que pusiste",
        line=dict(color=p.TEXT_SECONDARY, width=2, dash="dot", shape="hv"),
        hovertemplate=f"Pusiste: {simbolo} %{{y:{decimales}}}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=valor.index, y=valor.values, mode="lines", name="Valor de la cartera",
        line=dict(color=p.ACCENT, width=2.2),
        hovertemplate=f"%{{x|%d/%m/%Y}}<br>Valor: {simbolo} %{{y:{decimales}}}<extra></extra>",
    ))
    if operaciones is not None and not operaciones.empty:
        col_valor = "valor_dia_usd" if moneda == "USD" else "valor_dia_ars"
        col_monto = "monto_usd" if moneda == "USD" else "monto_ars"
        for accion, simbolo_marca, nombre in (("COMPRA", "triangle-up", "Compra"), ("VENTA", "triangle-down", "Venta")):
            ops = operaciones[(operaciones["accion"] == accion) & (operaciones["fecha"] >= valor.index[0])]
            if ops.empty:
                continue
            detalle = [
                f"{nombre} {r.ticker}: {formato.fmt(r.cantidad, ',.0f')} a {formato.fmt(r.precio, ',.2f')} {r.moneda}"
                f"<br>{'Pusiste' if accion == 'COMPRA' else 'Sacaste'} {formato.moneda(abs(getattr(r, col_monto)), moneda)}"
                for r in ops.itertuples()
            ]
            fig.add_trace(go.Scatter(
                x=ops["fecha"], y=ops[col_valor], mode="markers", name=nombre,
                marker=dict(symbol=simbolo_marca, size=11, color=p.TEXT_PRIMARY if accion == "COMPRA" else p.WARNING,
                            line=dict(color=p.BG_DARK, width=1.5)),
                text=detalle, hovertemplate="%{x|%d/%m/%Y}<br>%{text}<extra></extra>",
            ))
    if len(valor):
        ultimo = valor.iloc[-1]
        fig.add_annotation(
            x=valor.index[-1], y=ultimo, text=f"<b>{formato.moneda(ultimo, moneda, 0 if moneda == 'ARS' else 2)}</b>",
            showarrow=True, arrowhead=0, ax=-10, ay=-30, xanchor="right",
            font=dict(family=p.FONT_FAMILY_MONO, color=p.ACCENT, size=12),
            bgcolor=p.BG_PANEL_LIGHT, bordercolor=p.ACCENT, borderwidth=1, borderpad=4,
        )
    fig.update_layout(**p.plotly_layout_defaults(altura=360), title=titulo, hovermode="x unified")
    fig.update_layout(legend=dict(orientation="h", y=-0.12, font=dict(color=p.TEXT_SECONDARY)))
    fig.update_xaxes(tickformat="%m/%Y", dtick="M1")
    return fig


def composicion_en_el_tiempo(pesos: pd.DataFrame, titulo: str = "", max_series: int = 7) -> go.Figure:
    """Áreas apiladas al 100 % con el peso de cada activo día por día. El color
    sigue al ticker (orden por peso promedio, fijo para el período) y más allá
    de `max_series` se agrupa en "Otros"."""
    pesos = pesos.loc[:, (pesos > 0).any()]
    orden = pesos.mean().sort_values(ascending=False).index.tolist()
    if len(orden) > max_series:
        principales = orden[: max_series - 1]
        pesos = pesos[principales].assign(Otros=pesos[orden[max_series - 1:]].sum(axis=1))
        orden = principales + ["Otros"]
    fig = go.Figure()
    for i, col in enumerate(orden):
        color = p.CHART_SEQUENCE[i % len(p.CHART_SEQUENCE)] if col != "Otros" else p.TEXT_MUTED
        fig.add_trace(go.Scatter(
            x=pesos.index, y=pesos[col] * 100, mode="lines", name=col, stackgroup="uno",
            line=dict(width=0.5, color=p.BG_DARK), fillcolor=color,
            hovertemplate=f"{col}: " + "%{y:.1f} %<extra></extra>",
        ))
    fig.update_layout(**p.plotly_layout_defaults(altura=320), title=titulo, hovermode="x unified")
    fig.update_yaxes(range=[0, 100], ticksuffix=" %")
    fig.update_xaxes(tickformat="%m/%Y", dtick="M1")
    return fig
