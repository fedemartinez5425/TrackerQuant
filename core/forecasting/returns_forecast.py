"""
Forecasting de RETORNOS de cartera -- con una honestidad estadística que
no siempre se ve en herramientas similares: no existe un modelo con
evidencia sólida de predecir la DIRECCIÓN del retorno a corto plazo (es
básicamente la hipótesis de mercados eficientes en su forma débil). Lo
que sí se puede estimar razonablemente es el RANGO probable de resultados,
combinando:

  retorno esperado = deriva histórica (mu) × horizonte
  banda de incertidumbre = ± z × volatilidad pronosticada (GARCH) × √horizonte

Esto es un "cono de incertidumbre" (random walk with drift), no una
predicción de que "va a subir X%". Se muestra así de explícito en la UI.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

Z_68 = 1.0   # ~1 desvío estándar
Z_95 = 1.96  # ~2 desvíos estándar


def proyectar_retorno_acumulado(
    retornos: pd.Series, horizonte_dias: int, vol_anual_forecast: float
) -> dict:
    """Deriva (mu diario histórico × horizonte) + banda de incertidumbre
    usando la volatilidad pronosticada (no la histórica) para que la banda
    refleje el régimen de riesgo actual, no el promedio de todo el pasado."""
    mu_diario = float(retornos.dropna().mean())
    retorno_esperado = mu_diario * horizonte_dias

    vol_diaria_forecast = vol_anual_forecast / np.sqrt(252)
    desvio_horizonte = vol_diaria_forecast * np.sqrt(horizonte_dias)

    return {
        "retorno_esperado_pct": retorno_esperado,
        "banda_68_inf": retorno_esperado - Z_68 * desvio_horizonte,
        "banda_68_sup": retorno_esperado + Z_68 * desvio_horizonte,
        "banda_95_inf": retorno_esperado - Z_95 * desvio_horizonte,
        "banda_95_sup": retorno_esperado + Z_95 * desvio_horizonte,
        "horizonte_dias": horizonte_dias,
    }


def proyectar_valor_cartera(proyeccion_retorno: dict, valor_actual: float) -> dict:
    """Convierte la proyección de retorno % en montos $ sobre el valor actual."""
    return {
        clave: valor_actual * (1 + valor) if clave != "horizonte_dias" else valor
        for clave, valor in proyeccion_retorno.items()
    }


def cono_incertidumbre(
    retornos: pd.Series, forecast_path_vol_anual: pd.Series, valor_actual: float
) -> pd.DataFrame:
    """Arma el 'cono' día a día (para graficar) usando la volatilidad
    pronosticada específica de cada día del horizonte (no un solo número
    fijo) -- así el cono se ensancha de forma consistente con el modelo."""
    mu_diario = float(retornos.dropna().mean())
    filas = []
    for dia, vol_anual_dia in forecast_path_vol_anual.items():
        vol_diaria = vol_anual_dia / np.sqrt(252)
        desvio_acum = vol_diaria * np.sqrt(dia)
        retorno_acum = mu_diario * dia
        filas.append(
            {
                "dia": dia,
                "esperado": valor_actual * (1 + retorno_acum),
                "banda_68_inf": valor_actual * (1 + retorno_acum - Z_68 * desvio_acum),
                "banda_68_sup": valor_actual * (1 + retorno_acum + Z_68 * desvio_acum),
                "banda_95_inf": valor_actual * (1 + retorno_acum - Z_95 * desvio_acum),
                "banda_95_sup": valor_actual * (1 + retorno_acum + Z_95 * desvio_acum),
            }
        )
    return pd.DataFrame(filas).set_index("dia")
