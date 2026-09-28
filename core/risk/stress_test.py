"""
Test de estrés de un solo factor: estima el impacto de una caída del
benchmark (SPY por default) usando el beta histórico de cada activo.
Réplica directa de la pestaña "Estrés" del Excel original.

Limitación (igual que en el Excel, y hay que decirla siempre):
no captura shocks propios de cada activo, y las correlaciones suelen
dispararse durante las crisis, así que el impacto real puede ser peor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calcular_beta(retornos_activo: pd.Series, retornos_benchmark: pd.Series) -> float | None:
    df = pd.concat([retornos_activo, retornos_benchmark], axis=1).dropna()
    if len(df) < 20:  # muy pocos datos para confiar en el beta
        return None
    cov = df.cov().iloc[0, 1]
    var_benchmark = df.iloc[:, 1].var()
    if var_benchmark == 0:
        return None
    return float(cov / var_benchmark)


def betas_por_activo(retornos: pd.DataFrame, benchmark_ticker: str) -> dict[str, float | None]:
    if benchmark_ticker not in retornos.columns:
        return {}
    bench = retornos[benchmark_ticker]
    return {
        t: calcular_beta(retornos[t], bench)
        for t in retornos.columns
        if t != benchmark_ticker
    }


def beta_ponderado_cartera(betas: dict[str, float | None], pesos: dict[str, float]) -> float | None:
    pares = [(betas[t], pesos[t]) for t in betas if betas.get(t) is not None and t in pesos]
    if not pares:
        return None
    total_peso = sum(p for _, p in pares)
    if total_peso == 0:
        return None
    return sum(b * p for b, p in pares) / total_peso


def escenarios_estres(
    beta_cartera: float | None, valor_cartera: float, shocks: tuple = (-0.10, -0.20, -0.30, -0.34)
) -> list[dict]:
    filas = []
    etiquetas = {
        -0.10: "Caída del benchmark -10%",
        -0.20: "Caída del benchmark -20%",
        -0.30: "Caída del benchmark -30%",
        -0.34: "Crash tipo Marzo 2020 (-34%)",
    }
    for shock in shocks:
        impacto_pct = beta_cartera * shock if beta_cartera is not None else None
        impacto_pesos = impacto_pct * valor_cartera if impacto_pct is not None else None
        filas.append(
            {
                "Escenario": etiquetas.get(shock, f"Shock {shock:.0%}"),
                "Shock Benchmark": shock,
                "Impacto Estimado %": impacto_pct,
                "Impacto Estimado $": impacto_pesos,
            }
        )
    return filas
