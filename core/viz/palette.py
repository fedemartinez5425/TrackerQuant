"""
Fuente única de verdad para colores en toda la app. Ningún gráfico define
sus propios colores sueltos -- todos importan de acá, así la identidad
visual queda 100% consistente (pedido explícito: "colores de los gráficos
consistentes y con buenos degradados").

Paleta: negro/grafito profundo + verde menta como acento único, en la
línea de un panel de riesgo cuantitativo profesional ("Data Finance").
"""
from __future__ import annotations

# ---------- Base ----------
BG_DARK = "#070B0A"
BG_PANEL = "#0E1613"
BG_PANEL_LIGHT = "#131F1B"
BORDER = "rgba(0, 232, 168, 0.16)"
BORDER_SOLID = "#1C2E28"

TEXT_PRIMARY = "#EAF6F1"
TEXT_SECONDARY = "#7C9089"
TEXT_MUTED = "#4E5F58"

# ---------- Acento de marca ----------
ACCENT = "#00E8A8"           # verde menta -- KPIs, nav activo, línea principal
ACCENT_DIM = "#0B4A3B"       # verde profundo -- fondos de barra, hover suave
ACCENT_GLOW = "rgba(0, 232, 168, 0.35)"

# ---------- Semántico (semáforo / P&L) ----------
SUCCESS = "#00E8A8"
WARNING = "#FFC24B"
DANGER = "#FF5C6C"

# ---------- Escala categórica para gráficos multi-serie (donut, barras) ----------
# De más prominente (verde brillante) a más neutro (gris), como en el
# donut de referencia: siempre en este orden para que la serie más grande
# sea siempre la más "viva".
CHART_SEQUENCE = [
    "#00E8A8",  # menta brillante
    "#00B888",
    "#048C6B",
    "#0B5F4D",
    "#1F4A40",
    "#3E5C55",
    "#5C6E68",
]

# ---------- Escala continua (heatmaps de correlación, degradados) ----------
# De pérdida (rojo) a neutro (grafito) a ganancia (menta) -- para
# correlación/ P&L con signo.
CHART_DIVERGING = [
    [0.0, DANGER],
    [0.5, "#1C2E28"],
    [1.0, ACCENT],
]

# Degradado mono-cromático (menta oscuro -> menta brillante), para barras
# de magnitud sin signo (ej. contribución al riesgo).
CHART_SEQUENTIAL = [
    [0.0, "#0B2A22"],
    [0.5, "#048C6B"],
    [1.0, ACCENT],
]

FONT_FAMILY = "Inter, sans-serif"
FONT_FAMILY_MONO = "JetBrains Mono, monospace"
FONT_FAMILY_DISPLAY = "Space Grotesk, sans-serif"


def plotly_layout_defaults(altura: int | None = None) -> dict:
    """Kwargs comunes para fig.update_layout(**...) -- fondo, tipografía y
    grilla consistentes en TODOS los gráficos de la app."""
    layout = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": FONT_FAMILY, "color": TEXT_SECONDARY, "size": 12},
        "title_font": {"family": FONT_FAMILY_DISPLAY, "color": TEXT_PRIMARY, "size": 15},
        "legend": {"font": {"color": TEXT_SECONDARY}, "bgcolor": "rgba(0,0,0,0)"},
        "margin": {"l": 10, "r": 10, "t": 40, "b": 10},
        "xaxis": {"gridcolor": BORDER_SOLID, "zerolinecolor": BORDER_SOLID, "color": TEXT_SECONDARY},
        "yaxis": {"gridcolor": BORDER_SOLID, "zerolinecolor": BORDER_SOLID, "color": TEXT_SECONDARY},
        "hoverlabel": {
            "bgcolor": BG_PANEL_LIGHT,
            "font": {"family": FONT_FAMILY_MONO, "color": TEXT_PRIMARY},
            "bordercolor": ACCENT,
        },
    }
    if altura:
        layout["height"] = altura
    return layout


def color_semaforo(nivel: str) -> str:
    """Mapea el texto del semáforo (🟢/🟡/🔴 ...) a un color de marca."""
    if "ALTO" in nivel or "🔴" in nivel:
        return DANGER
    if "MEDIO" in nivel or "🟡" in nivel:
        return WARNING
    if "BAJO" in nivel or "🟢" in nivel:
        return SUCCESS
    return TEXT_SECONDARY
