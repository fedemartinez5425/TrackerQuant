"""
Arma la matriz de precios históricos que usan TODOS los cálculos de riesgo,
en una sola unidad monetaria (USD equivalente) para que sea correcto mezclar:

- CEDEARs: ya están en USD porque se usa el histórico de su ADR (ticker_usd).
- Acciones argentinas directas (ACCION_ARG, ej. PAMP comprada en pesos):
  se convierten día por día con el CCL histórico (no el de hoy).

Sin esto, mezclar el retorno en dólares de un CEDEAR con el retorno en
pesos de una acción directa daría un número de riesgo sin sentido
económico -- son dos monedas distintas.

La clave de cada columna del resultado es el ticker BCBA (siempre
disponible), no el ticker_usd (que las acciones directas no tienen).
"""
from __future__ import annotations

from typing import NamedTuple

import pandas as pd

from core import data_providers
from core.data_providers.ccl_provider import get_ccl_historico
from core.storage.models import TipoInstrumento


class InstrumentoRiesgo(NamedTuple):
    ticker: str
    tipo_instrumento: TipoInstrumento
    ticker_usd: str | None


def desde_posiciones(posiciones) -> list[InstrumentoRiesgo]:
    return [
        InstrumentoRiesgo(p.ticker, p.tipo_instrumento, p.ticker_usd)
        for p in posiciones
    ]


def historicos_usd_equivalente(
    instrumentos: list[InstrumentoRiesgo], period: str | None = None
) -> pd.DataFrame:
    frames = []
    ccl_hist = None
    necesita_ccl = any(i.tipo_instrumento == TipoInstrumento.ACCION_ARG for i in instrumentos)
    if necesita_ccl:
        ccl_hist = get_ccl_historico(period)

    for inst in instrumentos:
        if inst.tipo_instrumento == TipoInstrumento.CEDEAR and inst.ticker_usd:
            h = data_providers.get_history(inst.ticker_usd, period=period)
            if h is not None and not h.empty and inst.ticker_usd in h.columns:
                frames.append(h[inst.ticker_usd].rename(inst.ticker))
        else:  # ACCION_ARG
            ticker_bcba = f"{inst.ticker}.BA"
            h = data_providers.get_history(ticker_bcba, period=period)
            if h is not None and not h.empty and ccl_hist is not None and ticker_bcba in h.columns:
                combinado = pd.concat([h[ticker_bcba], ccl_hist], axis=1).ffill().dropna()
                if not combinado.empty:
                    frames.append((combinado[ticker_bcba] / combinado["CCL"]).rename(inst.ticker))

    if not frames:
        return pd.DataFrame()
    combinado = pd.concat(frames, axis=1)
    return combinado.ffill().dropna(how="all")
