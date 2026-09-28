"""
Identidad visual del Tracker Quant — Data Finance.

Concepto: panel de riesgo cuantitativo profesional, oscuro, con un único
acento verde menta. Inspirado en terminales de trading y dashboards de
market risk institucionales. Toda la paleta vive en core/viz/palette.py
(fuente única de verdad, también usada por los gráficos de Plotly).
"""
from core.viz import palette as p

CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {{
    --bg-base: {p.BG_DARK};
    --bg-panel: {p.BG_PANEL};
    --bg-panel-light: {p.BG_PANEL_LIGHT};
    --border: {p.BORDER};
    --border-solid: {p.BORDER_SOLID};
    --text-primary: {p.TEXT_PRIMARY};
    --text-secondary: {p.TEXT_SECONDARY};
    --accent: {p.ACCENT};
    --accent-dim: {p.ACCENT_DIM};
    --success: {p.SUCCESS};
    --warning: {p.WARNING};
    --danger: {p.DANGER};
}}

/* ---------- Base ---------- */
.stApp {{
    background:
        radial-gradient(ellipse 900px 500px at 15% -10%, rgba(0,232,168,0.06), transparent 60%),
        radial-gradient(ellipse 700px 500px at 100% 0%, rgba(0,232,168,0.04), transparent 55%),
        var(--bg-base);
    color: var(--text-primary);
    font-family: 'Inter', sans-serif;
}}

h1, h2, h3 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em;
    color: var(--text-primary) !important;
}}
h1 {{ font-weight: 700 !important; }}

p, span, label, li, div {{ color: var(--text-primary); }}
[data-testid="stCaptionContainer"], .stCaption, small {{ color: var(--text-secondary) !important; }}

/* ---------- Sidebar: panel de control ---------- */
[data-testid="stSidebar"] {{
    background: var(--bg-panel);
    border-right: 1px solid var(--border-solid);
}}
[data-testid="stSidebar"] * {{ color: var(--text-primary); }}

/* Links de navegación (st.navigation) */
[data-testid="stSidebarNav"] a, [data-testid="stSidebarNavLink"] {{
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    border-radius: 8px;
    transition: background 0.15s ease, color 0.15s ease;
}}
[data-testid="stSidebarNav"] a:hover, [data-testid="stSidebarNavLink"]:hover {{
    background: rgba(0, 232, 168, 0.08);
}}
[data-testid="stSidebarNav"] a[aria-current="page"], [data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(0, 232, 168, 0.12);
    border-left: 2px solid var(--accent);
    color: var(--accent) !important;
}}
[data-testid="stSidebarNav"] a[aria-current="page"] span, [data-testid="stSidebarNavLink"][aria-current="page"] span {{
    color: var(--accent) !important;
}}

/* Lockup de marca "DATA FINANCE" en el sidebar */
.df-lockup-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }}
.df-lockup-dot {{
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 10px {p.ACCENT_GLOW};
}}
.df-lockup {{
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    font-size: 1.15rem;
    letter-spacing: 0.02em;
    color: var(--text-primary);
    line-height: 1.1;
}}
.df-lockup span {{ color: var(--accent); }}
.df-sublockup {{
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin: 0 0 0.9rem 17px;
}}
.df-footer-signature {{
    font-family: 'Inter', sans-serif;
    font-size: 0.7rem;
    color: var(--text-secondary);
    text-align: center;
    line-height: 1.5;
    opacity: 0.85;
}}
.df-footer-signature b {{ color: var(--accent); }}

/* ---------- Métricas: paneles KPI estilo BI ---------- */
[data-testid="stMetric"] {{
    background: linear-gradient(155deg, var(--bg-panel-light) 0%, var(--bg-panel) 100%);
    border: 1px solid var(--border-solid);
    border-radius: 12px;
    padding: 1rem 1.1rem;
    box-shadow: 0 0 0 1px rgba(0,232,168,0.03) inset;
    transition: border-color 0.2s ease;
}}
[data-testid="stMetric"]:hover {{ border-color: rgba(0,232,168,0.35); }}
[data-testid="stMetricLabel"] {{
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    color: var(--text-secondary) !important;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}
[data-testid="stMetricValue"] {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    font-size: 1.7rem !important;
}}
[data-testid="stMetricDelta"] {{ font-family: 'JetBrains Mono', monospace !important; }}

/* ---------- Botones ---------- */
.stButton > button, [data-testid="stFormSubmitButton"] button {{
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    border-radius: 8px;
    border: 1px solid var(--border-solid);
    background: var(--bg-panel-light);
    color: var(--text-primary);
    transition: all 0.15s ease;
}}
.stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover {{
    border-color: var(--accent);
    color: var(--accent);
}}
button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {{
    background: var(--accent) !important;
    border: 1px solid var(--accent) !important;
    color: #06110D !important;
    font-weight: 700;
    box-shadow: 0 0 16px {p.ACCENT_GLOW};
}}
button[kind="primary"]:hover {{ filter: brightness(1.1); }}

/* Botón de cerrar sesión: ghost sutil, tinte rojo al hover */
[data-testid="stSidebar"] .stButton > button {{
    width: 100%;
    background: transparent;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    border-color: var(--danger);
    color: var(--danger);
}}

/* ---------- Inputs ---------- */
.stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
.stSelectbox [data-baseweb="select"] > div {{
    background: var(--bg-panel-light) !important;
    border: 1px solid var(--border-solid) !important;
    border-radius: 6px !important;
    color: var(--text-primary) !important;
    font-family: 'JetBrains Mono', monospace !important;
}}
.stTextInput input:focus, .stNumberInput input:focus {{ border-color: var(--accent) !important; }}

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"] {{ border-bottom: 1px solid var(--border-solid); gap: 1.5rem; }}
.stTabs [data-baseweb="tab"] {{ font-family: 'Inter', sans-serif; font-weight: 500; color: var(--text-secondary); }}
.stTabs [aria-selected="true"] {{ color: var(--accent) !important; border-bottom-color: var(--accent) !important; }}

/* ---------- Dataframes ---------- */
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    border: 1px solid var(--border-solid);
    border-radius: 10px;
    overflow: hidden;
}}
[data-testid="stDataFrame"] * {{ font-family: 'JetBrains Mono', monospace !important; font-size: 0.85rem; }}

/* ---------- Expander / Alerts / Divider ---------- */
[data-testid="stExpander"] {{ background: var(--bg-panel); border: 1px solid var(--border-solid); border-radius: 10px; }}
[data-testid="stAlert"] {{ border-radius: 10px; border-width: 1px; border-style: solid; }}
hr {{ border-color: var(--border-solid) !important; }}

/* ---------- Chrome de Streamlit ---------- */
footer {{ visibility: hidden; }}
#MainMenu {{ visibility: hidden; }}

/* ---------- Scrollbar ---------- */
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: var(--bg-base); }}
::-webkit-scrollbar-thumb {{ background: var(--border-solid); border-radius: 5px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--accent); }}
"""


def inject(st) -> None:
    """Inyecta el CSS global. Llamar una sola vez en app.py."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def sidebar_header(st) -> None:
    """Lockup 'DATA FINANCE' + firma de Fede Martinez en el sidebar."""
    st.markdown(
        """
        <div class="df-lockup-row">
            <div class="df-lockup-dot"></div>
            <div class="df-lockup">DATA<span>FINANCE</span></div>
        </div>
        <div class="df-sublockup">Tracker Quant · Risk Analytics</div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_footer(st) -> None:
    st.markdown(
        """
        <div class="df-footer-signature">
        Hecho por <b>Fede Martínez</b><br>Data Finance · YouTube
        </div>
        """,
        unsafe_allow_html=True,
    )
