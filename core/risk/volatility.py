from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def retorno_diario_cartera(retornos_activos: pd.DataFrame, pesos: dict[str, float]) -> pd.Series:
    """Retorno diario ponderado de la cartera (equivalente a la columna B de la
    pestaña 'Riesgo' del Excel original)."""
    tickers = [t for t in pesos if t in retornos_activos.columns]
    if not tickers:
        return pd.Series(dtype=float)
    pesos_arr = pd.Series({t: pesos[t] for t in tickers})
    return (retornos_activos[tickers] * pesos_arr).sum(axis=1)


def indice_base_100(retorno_cartera: pd.Series) -> pd.Series:
    """Cómo hubiera evolucionado $100 con los pesos de HOY a lo largo del historial."""
    return 100 * (1 + retorno_cartera).cumprod()


def volatilidad_anualizada(retorno_cartera: pd.Series) -> float | None:
    if retorno_cartera.empty or retorno_cartera.std() == 0:
        return None
    return float(retorno_cartera.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def semaforo_riesgo(vol_anualizada: float | None, concentracion_top2: float | None) -> str:
    """Replica la lógica de semáforo del Excel: rojo si vol > 40% o si las 2
    posiciones más grandes concentran > 75% del riesgo."""
    if vol_anualizada is None:
        return "🔲 SIN DATOS"
    concentracion_top2 = concentracion_top2 or 0
    if vol_anualizada > 0.40 or concentracion_top2 > 0.75:
        return "🔴 RIESGO ALTO"
    if vol_anualizada > 0.25 or concentracion_top2 > 0.55:
        return "🟡 RIESGO MEDIO"
    return "🟢 RIESGO BAJO"
