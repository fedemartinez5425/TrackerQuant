from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def pesos_disponibles(pesos: dict[str, float], columnas) -> dict[str, float]:
    """Pesos de los tickers que SÍ tienen histórico, re-normalizados para que
    sumen lo mismo que el total original. Si un activo no tiene datos, su
    peso se reparte entre el resto en vez de contarse como 0% de retorno
    (que subestimaba el riesgo)."""
    presentes = {t: w for t, w in pesos.items() if t in columnas and w}
    total_original = sum(w for w in pesos.values() if w)
    total_presente = sum(presentes.values())
    if not presentes or not total_presente:
        return {}
    factor = total_original / total_presente
    return {t: w * factor for t, w in presentes.items()}


def retorno_diario_cartera(retornos_activos: pd.DataFrame, pesos: dict[str, float]) -> pd.Series:
    """Retorno diario ponderado de la cartera (equivalente a la columna B de la
    pestaña 'Riesgo' del Excel original). Los días con algún retorno
    faltante se descartan en vez de tratarlos como 0%."""
    pesos_ok = pesos_disponibles(pesos, retornos_activos.columns)
    if not pesos_ok:
        return pd.Series(dtype=float)
    tickers = list(pesos_ok)
    pesos_arr = pd.Series(pesos_ok)
    datos = retornos_activos[tickers].dropna()
    return (datos * pesos_arr).sum(axis=1)


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
