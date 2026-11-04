"""
Números en formato argentino en toda la app: `$ 1.234.567,89`, `12,5 %`.
Python formatea al estilo inglés (1,234.56); acá se usa la misma
especificación de format() y se cambian los separadores al final.
"""
from __future__ import annotations

import math

_SEPARADORES_AR = str.maketrans({",": ".", ".": ","})


def a_ar(texto: str) -> str:
    """'1,234.56' -> '1.234,56' y '12.5%' -> '12,5 %'."""
    return texto.translate(_SEPARADORES_AR).replace("%", " %")


def fmt(valor, spec: str, vacio: str = "—") -> str:
    """format(valor, spec) en formato argentino. None/NaN -> '—'."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return vacio
    return a_ar(format(valor, spec))


def moneda(valor, moneda_: str = "ARS", decimales: int = 2) -> str:
    if valor is None:
        return "—"
    simbolo = "US$" if moneda_ == "USD" else "$"
    return f"{simbolo} {fmt(valor, f',.{decimales}f')}"


def pct(valor, decimales: int = 2, signo: bool = False) -> str:
    """0.1234 -> '12,34 %'."""
    return fmt(valor, f"{'+' if signo else ''}.{decimales}%")


def estilo(patron: str):
    """Patrón de Styler ('{:.1%}', '$ {:,.2f}') -> función que formatea en AR.
    Para pandas Styler.format, que acepta funciones por columna."""
    def _formatear(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "—"
        try:
            return a_ar(patron.format(v))
        except (ValueError, TypeError):
            return str(v)
    return _formatear
