from __future__ import annotations

import pandas as pd


def matriz_correlacion(retornos: pd.DataFrame) -> pd.DataFrame:
    return retornos.corr()


def correlacion_promedio_simple(matriz: pd.DataFrame) -> float | None:
    """Promedio de la correlación fuera de la diagonal (igual que el Excel)."""
    n = matriz.shape[0]
    if n < 2:
        return None
    suma = matriz.values.sum() - n  # resta la diagonal (todos 1)
    cantidad_pares = n * n - n
    return float(suma / cantidad_pares) if cantidad_pares else None


def correlacion_promedio_ponderada(matriz: pd.DataFrame, pesos: dict[str, float]) -> float | None:
    """Pondera cada correlación por el producto de los pesos de cartera de ese par
    (si AMZN y SHOP son el 50% de la cartera, su correlación pesa más)."""
    tickers = [t for t in matriz.columns if t in pesos]
    if len(tickers) < 2:
        return None

    numerador = 0.0
    denominador = 0.0
    for i in tickers:
        for j in tickers:
            if i == j:
                continue
            w = pesos[i] * pesos[j]
            numerador += matriz.loc[i, j] * w
            denominador += w

    return float(numerador / denominador) if denominador else None


def lectura_diversificacion(corr_promedio: float | None) -> str:
    if corr_promedio is None:
        return "Sin datos suficientes para evaluar diversificación."
    if corr_promedio > 0.7:
        return "🔴 Tu cartera está poco diversificada: la mayoría de tus activos se mueven juntos."
    if corr_promedio > 0.4:
        return "🟡 Diversificación moderada: hay margen para bajar la correlación entre posiciones."
    return "🟢 Buena diversificación: tus activos no dependen tanto unos de otros."
