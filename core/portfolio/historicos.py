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

Calendarios: BCBA y NYSE tienen feriados distintos. Antes se rellenaba
hacia adelante (ffill) el precio del mercado cerrado, lo que generaba
retornos de 0% falsos ese día y un salto al siguiente: eso SUBESTIMA la
volatilidad, la correlación y el beta. Ahora `alinear_dias_comunes` deja
solo los días en que cotizaron todos los activos, así cada retorno mide el
movimiento real entre dos días con precio de todos.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

import pandas as pd

from core import data_providers
from core.data_providers.ccl_provider import get_ccl_historico
from core.storage.models import TipoInstrumento

logger = logging.getLogger(__name__)

MIN_DIAS_ALINEADOS = 120  # ~6 meses hábiles: mínimo razonable para medir riesgo


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
    """Precios en USD equivalente, una columna por ticker BCBA. NO alinea
    calendarios (cada columna tiene NaN en los días que su mercado no
    operó): usar `alinear_dias_comunes` antes de calcular retornos."""
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
                precio_ars = h[ticker_bcba].dropna()
                # El CCL es un tipo de cambio (no "cotiza" por sí mismo): para
                # cada día con precio en BCBA se usa el último CCL conocido.
                ccl_alineado = ccl_hist.reindex(ccl_hist.index.union(precio_ars.index)).ffill().reindex(precio_ars.index)
                serie = (precio_ars / ccl_alineado).dropna()
                if not serie.empty:
                    frames.append(serie.rename(inst.ticker))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).dropna(how="all")


def alinear_dias_comunes(precios: pd.DataFrame, min_dias: int = MIN_DIAS_ALINEADOS) -> pd.DataFrame:
    """Deja solo los días en que TODAS las columnas tienen precio (descarta
    feriados de un solo mercado en vez de inventar un precio).

    Si algún activo tiene muy poca historia (ej. empezó a cotizar hace poco)
    y eso deja menos de `min_dias` días, ese activo se excluye para no
    achicar la ventana de toda la cartera; los excluidos quedan en
    `resultado.attrs["excluidos"]` para poder avisarlo en la UI."""
    if precios is None or precios.empty:
        return pd.DataFrame() if precios is None else precios

    df = precios.dropna(axis=1, how="all")
    excluidos: list[str] = []
    while True:
        alineado = df.dropna()
        if len(alineado) >= min_dias or df.shape[1] <= 1:
            break
        inicio_por_columna = df.apply(lambda s: s.first_valid_index())
        mas_corta = inicio_por_columna.idxmax()
        largo_sin_ella = len(df.drop(columns=[mas_corta]).dropna())
        if largo_sin_ella <= len(alineado):
            break  # sacarla no ayuda: el problema no es la historia corta
        excluidos.append(mas_corta)
        df = df.drop(columns=[mas_corta])

    if excluidos:
        logger.warning("Excluidos del cálculo de riesgo por historia insuficiente: %s", ", ".join(excluidos))
    alineado = alineado.copy()
    alineado.attrs["excluidos"] = excluidos
    return alineado
