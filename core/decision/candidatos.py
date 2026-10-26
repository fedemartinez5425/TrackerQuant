"""
Evaluación de candidatos para sumar a la cartera.

La pregunta que responde: "si pongo X% de la cartera en este activo
(achicando todo lo demás en proporción), ¿qué le pasa a la vol, al Sharpe y
al max drawdown de la cartera en 1 y 3 años?", más con qué posición se
pisa (correlación).

Precios: USD equivalente (salida de `historicos_usd_equivalente`), una
columna por ticker. Cada candidato se evalúa sobre los días en que
cotizaron él y TODAS las tenencias (dropna, nunca forward-fill): así un
candidato con historia corta no achica la ventana de los demás.

⚠️ Es un backtest: mira hacia atrás. Con sesgo de supervivencia, sacar un
activo que cayó siempre "mejora" el pasado, y sumar uno que subió también.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config.settings import settings
from core import data_providers
from core.performance.metrics import VENTANAS_ANIOS, metricas_cartera
from core.risk.volatility import retorno_diario_cartera
from core.storage.models import TipoInstrumento

logger = logging.getLogger(__name__)

PESO_OBJETIVO_DEFAULT = 0.10
METRICAS_DELTA = ("vol", "sharpe", "max_dd")


def pesos_con_candidato(pesos_actuales: dict[str, float], candidato: str, peso_objetivo: float) -> dict[str, float]:
    """Escala la cartera actual a (1 − peso_objetivo) y suma el candidato con
    peso_objetivo. Si el candidato ya está en cartera, se le suma encima."""
    total = sum(w for w in pesos_actuales.values() if w)
    if not total:
        return {candidato: 1.0}
    escala = (1 - peso_objetivo) / total
    nuevos = {t: w * escala for t, w in pesos_actuales.items() if w}
    nuevos[candidato] = nuevos.get(candidato, 0.0) + peso_objetivo
    return nuevos


def _delta(despues, antes) -> float | None:
    if despues is None or antes is None:
        return None
    return despues - antes


def evaluar_candidato(
    precios: pd.DataFrame,
    pesos_actuales: dict[str, float],
    candidato: str,
    peso_objetivo: float = PESO_OBJETIVO_DEFAULT,
    ventanas: tuple = VENTANAS_ANIOS,
    rf: float | None = None,
) -> dict:
    """Impacto de sumar `candidato` con `peso_objetivo` sobre la cartera.

    Devuelve: métricas antes/después, delta_{vol,sharpe,max_dd}_{n}a,
    corr_cartera, corr_posiciones (Series), mas_correlacionada y su
    correlación, y dias (cantidad de ruedas comunes usadas)."""
    tenencias = [t for t in pesos_actuales if pesos_actuales[t] and t in precios.columns]
    resultado: dict = {"ticker": candidato, "peso_objetivo": peso_objetivo}
    if candidato not in precios.columns or not tenencias:
        resultado["error"] = "Sin históricos del candidato o de la cartera."
        return resultado

    columnas = list(dict.fromkeys(tenencias + [candidato]))
    sub = precios[columnas].dropna()
    resultado["dias"] = len(sub)
    if len(sub) < 3:
        resultado["error"] = "Sin días en común entre el candidato y la cartera."
        return resultado

    pesos_base = {t: pesos_actuales[t] for t in tenencias}
    antes = metricas_cartera(sub, pesos_base, ventanas, rf)
    despues = metricas_cartera(sub, pesos_con_candidato(pesos_base, candidato, peso_objetivo), ventanas, rf)
    resultado["antes"], resultado["despues"] = antes, despues
    for n in ventanas:
        for metrica in METRICAS_DELTA:
            clave = f"{metrica}_{n}a"
            resultado[f"delta_{clave}"] = _delta(despues.get(clave), antes.get(clave))

    retornos = sub.pct_change().dropna()
    r_cartera = retorno_diario_cartera(retornos, pesos_base)
    resultado["corr_cartera"] = float(retornos[candidato].corr(r_cartera)) if not r_cartera.empty else None
    corr_pos = retornos.corr()[candidato].drop(labels=[candidato], errors="ignore").dropna()
    resultado["corr_posiciones"] = corr_pos
    if not corr_pos.empty:
        resultado["mas_correlacionada"] = str(corr_pos.idxmax())
        resultado["corr_mas_correlacionada"] = float(corr_pos.max())
    else:
        resultado["mas_correlacionada"] = None
        resultado["corr_mas_correlacionada"] = None
    return resultado


def rankear_candidatos(
    precios: pd.DataFrame,
    pesos_actuales: dict[str, float],
    candidatos: list[str],
    peso_objetivo: float = PESO_OBJETIVO_DEFAULT,
    ventanas: tuple = VENTANAS_ANIOS,
    rf: float | None = None,
) -> pd.DataFrame:
    """Una fila por candidato con los deltas y correlaciones, ordenado por
    delta de Sharpe a 3 años (mejor primero; sin dato al final)."""
    filas = []
    for c in candidatos:
        ev = evaluar_candidato(precios, pesos_actuales, c, peso_objetivo, ventanas, rf)
        fila = {"ticker": c}
        for n in ventanas:
            for metrica in METRICAS_DELTA:
                fila[f"delta_{metrica}_{n}a"] = ev.get(f"delta_{metrica}_{n}a")
        fila["corr_cartera"] = ev.get("corr_cartera")
        fila["mas_correlacionada"] = ev.get("mas_correlacionada")
        fila["corr_mas_correlacionada"] = ev.get("corr_mas_correlacionada")
        fila["dias"] = ev.get("dias")
        fila["error"] = ev.get("error")
        filas.append(fila)
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas).set_index("ticker")
    numericas = [c for c in df.columns if c.startswith("delta_") or c.startswith("corr_")]
    df[numericas] = df[numericas].astype(float)
    orden = "delta_sharpe_3a" if "delta_sharpe_3a" in df.columns else f"delta_sharpe_{ventanas[-1]}a"
    return df.sort_values(orden, ascending=False, na_position="last")


# ---------------- Precio por unidad ----------------
def precio_unidad_ars(item, ccl: float | None = None, ratio: float | None = None) -> float | None:
    """Precio de 1 unidad en pesos.

    - CEDEAR: precio ADR (USD) × CCL / ratio. El ratio sale del item o, si
      no lo tiene, del listado de Comafi.
    - Acción argentina: precio BCBA.
    `item` es cualquier objeto con ticker, tipo_instrumento, ticker_usd y
    ratio_cedear (WatchlistItem o Instrumento)."""
    if item.tipo_instrumento == TipoInstrumento.CEDEAR:
        if ccl is None:
            from core.data_providers.ccl_provider import get_ccl_automatico

            info = get_ccl_automatico()
            ccl = info["valor"] if info else None
        ratio = ratio or item.ratio_cedear
        if not ratio:
            from core.data_providers.comafi_ratios import obtener_ratio

            ratio = obtener_ratio(item.ticker, settings.CEDEAR_RATIOS_FILE)
        precio_adr = data_providers.get_price(item.ticker_usd or item.ticker)
        if not (ccl and ratio and precio_adr):
            return None
        return precio_adr * ccl / ratio
    return data_providers.get_price(f"{item.ticker}.BA")


def peso_de_una_unidad(precio_unidad: float | None, valor_cartera: float | None) -> float | None:
    """Precio de 1 unidad / valor actual de la cartera (ej.: 1 META ≈ 44% de
    una cartera de $106.000). Si supera el peso objetivo, no se puede llegar
    a ese peso sin pasarse."""
    if not precio_unidad or not valor_cartera:
        return None
    return precio_unidad / valor_cartera


def unidades_para_peso(precio_unidad: float | None, valor_cartera: float | None, peso_objetivo: float) -> int | None:
    """Unidades enteras para acercarse a peso_objetivo de la cartera
    resultante (redondeo hacia abajo; puede dar 0)."""
    if not precio_unidad or not valor_cartera or not (0 < peso_objetivo < 1):
        return None
    monto = valor_cartera * peso_objetivo / (1 - peso_objetivo)
    return int(np.floor(monto / precio_unidad))
