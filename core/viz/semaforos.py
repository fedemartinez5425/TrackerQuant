"""
Semáforos para tablas: a cada número le asigna verde / amarillo / rojo según
umbrales fijos, y lo pinta con pandas Styler (st.dataframe respeta los
colores del Styler; el CSS global no llega a las celdas porque se dibujan
en canvas).

Los umbrales de volatilidad y correlación son los mismos que usan
`core/risk/volatility.semaforo_riesgo`, `core/risk/correlation` y
`core/insights/rules_engine`, para que la tabla y el Dashboard digan lo mismo.

Sin Streamlit: solo pandas, así se testea sin levantar la app.
"""
from __future__ import annotations

import math
from typing import Callable

import pandas as pd

from core.viz import palette as p

VERDE, AMARILLO, ROJO = "verde", "amarillo", "rojo"
EMOJI = {VERDE: "🟢", AMARILLO: "🟡", ROJO: "🔴"}
LEYENDA = "🟢 bien · 🟡 mirar · 🔴 atención"

# ---------------- Umbrales ----------------
VOL_MEDIA, VOL_ALTA = 0.25, 0.40
PESO_MEDIO, PESO_ALTO = 0.15, 0.25
CORR_MEDIA, CORR_ALTA = 0.4, 0.7
DD_MEDIO, DD_ALTO = -0.20, -0.35
PRIMA_MEDIA, PRIMA_ALTA = 0.03, 0.06
RSI_SOBREVENDIDO, RSI_SOBRECOMPRADO = 30, 70
ERROR_PP_MEDIO, ERROR_PP_ALTO = 2.0, 5.0


def _numero(valor) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _escalones(v: float, medio: float, alto: float) -> str:
    """Más alto = peor: <= medio verde, <= alto amarillo, > alto rojo
    (mismos cortes que `semaforo_riesgo`: vol > 25% recién es MEDIO)."""
    if v <= medio:
        return VERDE
    return AMARILLO if v <= alto else ROJO


def signo(v: float) -> str | None:
    """Positivo es bueno (G/P, CAGR, Δ Sharpe, Δ Max DD)."""
    return VERDE if v > 0 else ROJO if v < 0 else None


def signo_inverso(v: float) -> str | None:
    """Negativo es bueno (Δ volatilidad)."""
    return signo(-v)


def volatilidad(v: float) -> str:
    return _escalones(v, VOL_MEDIA, VOL_ALTA)


def peso(v: float) -> str:
    return _escalones(v, PESO_MEDIO, PESO_ALTO)


def correlacion(v: float) -> str:
    return _escalones(v, CORR_MEDIA, CORR_ALTA)


def drawdown(v: float) -> str:
    """Valores negativos: −10% verde, −25% amarillo, −40% rojo."""
    return _escalones(-v, -DD_MEDIO, -DD_ALTO)


def prima(v: float) -> str:
    return _escalones(abs(v), PRIMA_MEDIA, PRIMA_ALTA)


def rsi(v: float) -> str:
    return VERDE if RSI_SOBREVENDIDO <= v <= RSI_SOBRECOMPRADO else ROJO


def error_pp(v: float) -> str:
    return _escalones(abs(v), ERROR_PP_MEDIO, ERROR_PP_ALTO)


REGLAS: dict[str, Callable[[float], str | None]] = {
    "signo": signo,
    "signo_inverso": signo_inverso,
    "volatilidad": volatilidad,
    "peso": peso,
    "correlacion": correlacion,
    "drawdown": drawdown,
    "prima": prima,
    "rsi": rsi,
    "error_pp": error_pp,
}


def nivel(valor, regla: str) -> str | None:
    """Nivel del semáforo, o None si el valor falta (NaN / None / texto)."""
    v = _numero(valor)
    return None if v is None else REGLAS[regla](v)


def css(nivel_: str | None) -> str:
    """Texto en el color del nivel; los rojos llevan además un fondo suave."""
    if nivel_ == VERDE:
        return f"color: {p.SUCCESS}"
    if nivel_ == AMARILLO:
        return f"color: {p.WARNING}"
    if nivel_ == ROJO:
        return f"color: {p.DANGER}; background-color: rgba(255, 92, 108, 0.12)"
    return ""


def estilar(tabla, reglas: dict[str, str]):
    """Aplica `{columna: regla}` a un DataFrame o Styler. Las columnas que
    no están en la tabla se ignoran. Devuelve un Styler."""
    styler = tabla.style if isinstance(tabla, pd.DataFrame) else tabla
    for columna, regla in reglas.items():
        if columna in styler.data.columns:
            styler = styler.map(lambda v, r=regla: css(nivel(v, r)), subset=[columna])
    return styler


def tabla(df: pd.DataFrame, formatos: dict[str, str] | None = None, reglas: dict[str, str] | None = None):
    """Styler listo para st.dataframe: formatos y semáforos solo de las
    columnas presentes (así una vista resumida reusa los mismos dicts)."""
    formatos = {c: f for c, f in (formatos or {}).items() if c in df.columns}
    return estilar(df.style.format(formatos, na_rep="—"), reglas or {})


def estilar_filas(tabla, reglas_por_fila: dict[str, str], columnas: list[str] | None = None):
    """Como `estilar`, pero la regla depende de la FILA (tablas con una
    métrica por fila, ej. 'Actual vs. Escenario')."""
    styler = tabla.style if isinstance(tabla, pd.DataFrame) else tabla
    columnas = columnas or list(styler.data.columns)
    for fila, regla in reglas_por_fila.items():
        if fila in styler.data.index:
            styler = styler.map(lambda v, r=regla: css(nivel(v, r)), subset=pd.IndexSlice[[fila], columnas])
    return styler


def senal(niveles) -> str:
    """Emoji del PEOR nivel de la lista (los None se ignoran)."""
    presentes = [n for n in niveles if n]
    for n in (ROJO, AMARILLO, VERDE):
        if n in presentes:
            return EMOJI[n]
    return ""


def columna_senal(df: pd.DataFrame, reglas: dict[str, str]) -> pd.Series:
    """Una señal por fila: el peor semáforo entre las columnas indicadas."""
    usadas = {c: r for c, r in reglas.items() if c in df.columns}
    return df.apply(lambda fila: senal(nivel(fila[c], r) for c, r in usadas.items()), axis=1)
