"""
Orquesta las funciones de core/risk/* para armar el resumen que se muestra
en el Dashboard, replicando la pestaña Dashboard del Excel original.
No reimplementa ninguna fórmula: solo llama a las funciones de cada módulo.
"""
from __future__ import annotations

import pandas as pd

from core.portfolio.attribution import contribucion_al_riesgo
from core.risk.correlation import (
    correlacion_promedio_ponderada,
    correlacion_promedio_simple,
    lectura_diversificacion,
    matriz_correlacion,
)
from core.risk.stress_test import beta_ponderado_cartera, betas_por_activo, escenarios_estres
from core.risk.var import cvar_historico, peor_dia_historico, var_en_pesos, var_historico
from core.risk.volatility import (
    indice_base_100,
    retorno_diario_cartera,
    semaforo_riesgo,
    volatilidad_anualizada,
)


def calcular_resumen_riesgo(
    historicos: pd.DataFrame,
    pesos: dict[str, float],
    valor_cartera: float,
    benchmark_ticker: str,
    stress_shocks: tuple = (-0.10, -0.20, -0.30, -0.34),
) -> dict:
    retornos = historicos.pct_change().dropna(how="all")
    retorno_cartera = retorno_diario_cartera(retornos, pesos)

    vol_anual = volatilidad_anualizada(retorno_cartera)

    contrib = (
        contribucion_al_riesgo(retornos, pesos) if not retornos.empty else pd.Series(dtype=float)
    )
    concentracion_top2 = (
        float(contrib.sort_values(ascending=False).iloc[:2].sum()) if len(contrib) >= 2 else None
    )

    var95 = var_historico(retorno_cartera, 0.95)
    var99 = var_historico(retorno_cartera, 0.99)
    cvar95 = cvar_historico(retorno_cartera, 0.95)
    cvar99 = cvar_historico(retorno_cartera, 0.99)
    peor_pct, peor_fecha = peor_dia_historico(retorno_cartera)

    matriz = matriz_correlacion(retornos[[t for t in pesos if t in retornos.columns]])
    corr_simple = correlacion_promedio_simple(matriz)
    corr_ponderada = correlacion_promedio_ponderada(matriz, pesos)

    betas = betas_por_activo(retornos, benchmark_ticker) if benchmark_ticker in retornos.columns else {}
    beta_cartera = beta_ponderado_cartera(betas, pesos)
    escenarios = escenarios_estres(beta_cartera, valor_cartera, shocks=stress_shocks)

    return {
        "retorno_cartera": retorno_cartera,
        "indice_cartera": indice_base_100(retorno_cartera) if not retorno_cartera.empty else retorno_cartera,
        "volatilidad_anualizada": vol_anual,
        "semaforo": semaforo_riesgo(vol_anual, concentracion_top2),
        "contribucion_riesgo": contrib,
        "concentracion_top2": concentracion_top2,
        "var_95_pct": var95,
        "var_95_usd": var_en_pesos(var95, valor_cartera),
        "var_99_pct": var99,
        "var_99_usd": var_en_pesos(var99, valor_cartera),
        "cvar_95_pct": cvar95,
        "cvar_95_usd": var_en_pesos(cvar95, valor_cartera),
        "cvar_99_pct": cvar99,
        "cvar_99_usd": var_en_pesos(cvar99, valor_cartera),
        "peor_dia_pct": peor_pct,
        "peor_dia_fecha": peor_fecha,
        "beta_cartera": beta_cartera,
        "correlacion_simple": corr_simple,
        "correlacion_ponderada": corr_ponderada,
        "lectura_diversificacion": lectura_diversificacion(
            corr_ponderada if corr_ponderada is not None else corr_simple
        ),
        "escenarios_estres": escenarios,
    }
