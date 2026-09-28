"""
Forecasting de volatilidad con GARCH(1,1) (librería `arch`, estándar de
la industria para esto -- no es una elección exótica).

Por qué GARCH y no otra cosa: la volatilidad de los retornos financieros
muestra "clustering" (períodos calmos y períodos turbulentos se agrupan)
-- eso es exactamente lo que GARCH modela explícitamente, a diferencia de
un simple promedio móvil. Es información real, no una caja negra: el
modelo tiene 3 parámetros (omega, alpha, beta) totalmente interpretables.

Nota de honestidad: esto pronostica VOLATILIDAD (qué tan grande puede ser
el próximo movimiento), no DIRECCIÓN (si sube o baja). Ver
returns_forecast.py para la diferencia.

Rendimiento: ajustar un GARCH(1,1) sobre ~750 observaciones diarias tarda
milisegundos -- el cuello de botella real es traer el histórico de
precios (ya cacheado en core/data_providers). Por eso acá no hace falta
ninguna capa extra de caché en disco/DB: alcanza con st.cache_data sobre
la función de más alto nivel, para no repetir el fit en cada rerun de
Streamlit dentro de la misma sesión.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from arch import arch_model

TRADING_DAYS_PER_YEAR = 252


def ajustar_garch(retornos: pd.Series):
    """Ajusta un GARCH(1,1) sobre los retornos diarios (en proporción, ej.
    0.01 = 1%). La librería `arch` trabaja mejor en escala porcentual
    (retornos * 100), así que la conversión se hace acá adentro."""
    retornos_pct = (retornos.dropna() * 100).reset_index(drop=True)
    modelo = arch_model(retornos_pct, vol="Garch", p=1, q=1, mean="Constant", dist="normal")
    return modelo.fit(disp="off")


def forecast_volatilidad_anualizada(resultado_garch, horizonte_dias: int) -> pd.Series:
    """Devuelve la volatilidad anualizada pronosticada para cada uno de los
    próximos `horizonte_dias` días hábiles."""
    forecast = resultado_garch.forecast(horizon=horizonte_dias, reindex=False)
    varianza_diaria_pct2 = forecast.variance.iloc[-1]  # en (retorno%)^2
    vol_diaria = np.sqrt(varianza_diaria_pct2) / 100  # de vuelta a proporción
    vol_anualizada = vol_diaria * np.sqrt(TRADING_DAYS_PER_YEAR)
    vol_anualizada.index = range(1, horizonte_dias + 1)
    return vol_anualizada


def volatilidad_condicional_historica(resultado_garch) -> pd.Series:
    """Serie de volatilidad condicional YA ESTIMADA por el modelo para cada
    día histórico (para graficar contra la volatilidad realizada real)."""
    vol_diaria = resultado_garch.conditional_volatility / 100
    return vol_diaria * np.sqrt(TRADING_DAYS_PER_YEAR)


def volatilidad_realizada_movil(retornos: pd.Series, ventana: int = 21) -> pd.Series:
    """Volatilidad realizada (rolling, no modelo) -- para comparar contra
    la condicional del GARCH y contra el forecast."""
    return retornos.rolling(ventana).std() * np.sqrt(TRADING_DAYS_PER_YEAR)


def clasificar_regimen(vol_actual: float | None, vol_promedio_historico: float | None) -> str:
    if vol_actual is None or not vol_promedio_historico:
        return "Sin datos suficientes"
    ratio = vol_actual / vol_promedio_historico
    if ratio > 1.3:
        return "🔴 Régimen de alta volatilidad (por encima de lo habitual)"
    if ratio < 0.7:
        return "🟢 Régimen de baja volatilidad (por debajo de lo habitual)"
    return "🟡 Régimen de volatilidad normal"


def resumen_forecast_volatilidad(retornos: pd.Series, horizonte_dias: int = 10) -> dict | None:
    """Orquesta todo: ajusta el modelo, pronostica, y arma el resumen que
    consume la página de Forecasting. Devuelve None si no hay suficientes
    datos (GARCH necesita un mínimo de historia para converger de forma confiable)."""
    retornos_validos = retornos.dropna()
    if len(retornos_validos) < 100:
        return None

    resultado = ajustar_garch(retornos_validos)
    vol_condicional = volatilidad_condicional_historica(resultado)
    vol_condicional.index = retornos_validos.index[-len(vol_condicional):]

    vol_realizada = volatilidad_realizada_movil(retornos_validos)
    forecast_path = forecast_volatilidad_anualizada(resultado, horizonte_dias)

    vol_actual = float(vol_condicional.iloc[-1])
    vol_promedio_historico = float(vol_realizada.dropna().mean()) if not vol_realizada.dropna().empty else None

    return {
        "vol_condicional_historica": vol_condicional,
        "vol_realizada_movil": vol_realizada,
        "forecast_path": forecast_path,  # índice 1..horizonte_dias
        "vol_actual": vol_actual,
        "vol_promedio_historico": vol_promedio_historico,
        "vol_n_dias": float(forecast_path.iloc[-1]),
        "regimen": clasificar_regimen(vol_actual, vol_promedio_historico),
        "parametros": {
            "omega": float(resultado.params.get("omega", float("nan"))),
            "alpha": float(resultado.params.get("alpha[1]", float("nan"))),
            "beta": float(resultado.params.get("beta[1]", float("nan"))),
        },
    }


def calcular_vol_realizada_ventana(retornos: pd.Series, fecha_inicio, dias_habiles: int) -> float | None:
    """Volatilidad anualizada REALIZADA en una ventana futura específica --
    usada para el backtest de forecasts pasados (ver core/forecasting/backtest.py)."""
    ventana = retornos[retornos.index >= pd.Timestamp(fecha_inicio)].iloc[:dias_habiles]
    if len(ventana) < max(5, dias_habiles // 2):
        return None
    return float(ventana.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
