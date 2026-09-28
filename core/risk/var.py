from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def var_historico(retorno_cartera: pd.Series, confianza: float = 0.95) -> float | None:
    """VaR histórico: el peor retorno del percentil (1-confianza) observado
    en la historia real. Simple, transparente, sin supuestos de distribución."""
    if retorno_cartera.empty:
        return None
    percentil = (1 - confianza) * 100
    return float(np.percentile(retorno_cartera.dropna(), percentil))


def var_parametrico(retorno_cartera: pd.Series, confianza: float = 0.95) -> float | None:
    """VaR paramétrico (asume normalidad): media - z * desvío.
    Menos robusto que el histórico ante colas gordas, pero rápido de calcular
    y útil como referencia cruzada."""
    if retorno_cartera.empty:
        return None
    media = retorno_cartera.mean()
    desvio = retorno_cartera.std()
    z = stats.norm.ppf(1 - confianza)
    return float(media + z * desvio)


def var_en_pesos(var_pct: float | None, valor_cartera: float) -> float | None:
    if var_pct is None:
        return None
    return var_pct * valor_cartera


def cvar_historico(retorno_cartera: pd.Series, confianza: float = 0.95) -> float | None:
    """CVaR / Expected Shortfall: promedio de las pérdidas en el peor (1-confianza)
    de los días. Más informativo que el VaR solo: no dice "el límite", dice
    "qué tan mal es en promedio cuando las cosas salen mal"."""
    if retorno_cartera.empty:
        return None
    umbral = var_historico(retorno_cartera, confianza)
    if umbral is None:
        return None
    cola = retorno_cartera[retorno_cartera <= umbral]
    if cola.empty:
        return None
    return float(cola.mean())


def peor_dia_historico(retorno_cartera: pd.Series) -> tuple[float, object] | tuple[None, None]:
    """Devuelve (retorno %, fecha) del peor día histórico de la cartera."""
    if retorno_cartera.empty:
        return None, None
    peor = retorno_cartera.min()
    fecha = retorno_cartera.idxmin()
    return float(peor), fecha


def resumen_var_cvar(retorno_cartera: pd.Series, valor_cartera: float, niveles=(0.95, 0.99)) -> list[dict]:
    filas = []
    for nivel in niveles:
        hist = var_historico(retorno_cartera, nivel)
        cvar = cvar_historico(retorno_cartera, nivel)
        filas.append(
            {
                "Confianza": f"{int(nivel * 100)}%",
                "VaR Histórico %": hist,
                "VaR Histórico $": var_en_pesos(hist, valor_cartera),
                "CVaR (Expected Shortfall) %": cvar,
                "CVaR (Expected Shortfall) $": var_en_pesos(cvar, valor_cartera),
            }
        )
    return filas

