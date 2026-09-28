"""
Contribución de cada posición al riesgo total de la cartera (MCTR:
Marginal Contribution To Risk). Responde la pregunta del texto original:
"¿qué porcentaje de mi riesgo total depende de esta posición?"
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calcular_retornos_diarios(precios: pd.DataFrame) -> pd.DataFrame:
    return precios.pct_change().dropna(how="all")


def contribucion_al_riesgo(retornos: pd.DataFrame, pesos: dict[str, float]) -> pd.Series:
    """
    Calcula la contribución porcentual de cada activo al riesgo (volatilidad) total
    de la cartera, usando la matriz de covarianza.

    MCTR_i = (w_i * (Cov @ w)_i) / (w' Cov w)
    """
    tickers = [t for t in pesos if t in retornos.columns]
    if len(tickers) < 1:
        return pd.Series(dtype=float)

    w = np.array([pesos[t] for t in tickers])
    cov = retornos[tickers].cov().values * 252  # anualizada

    varianza_cartera = w @ cov @ w
    if varianza_cartera <= 0:
        return pd.Series({t: 0.0 for t in tickers})

    contrib_marginal = cov @ w  # vector
    contrib_absoluta = w * contrib_marginal
    contrib_pct = contrib_absoluta / varianza_cartera

    return pd.Series(contrib_pct, index=tickers).sort_values(ascending=False)
