"""
Almacén de precios: los cierres diarios que guarda el ETL (pestaña `precios`)
en memoria, como una matriz ancha (fecha × ticker).

No sabe de dónde vienen los datos: la app le pasa un `cargador` (una
función que devuelve list[PrecioCierre], ej. get_repository().list_precios)
con `configurar()`. Sin cargador (tests, ETL) el almacén está vacío y todo
sigue funcionando contra Yahoo como antes.

Se relee cada `settings.PRICE_CACHE_TTL_SECONDS`; si la lectura falla
(Sheets caído) se conserva lo último leído.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable

import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)

# Margen al decidir si el almacén cubre un período (feriados al inicio de la ventana).
MARGEN_COBERTURA_DIAS = 10

_cargador: Callable[[], list] | None = None
_matriz: pd.DataFrame = pd.DataFrame()
_leido_en: float = 0.0
_actualizado_en: datetime | None = None
_error: str | None = None


def configurar(cargador: Callable[[], list] | None) -> None:
    global _cargador, _leido_en
    if cargador != _cargador:  # != y no "is not": cada get_repository().list_precios es un objeto nuevo
        _cargador = cargador
        _leido_en = 0.0


def invalidar() -> None:
    global _leido_en
    _leido_en = 0.0


def matriz_desde_precios(precios: list) -> tuple[pd.DataFrame, datetime | None]:
    """list[PrecioCierre] -> (matriz fecha × ticker, último actualizado_en)."""
    if not precios:
        return pd.DataFrame(), None
    largo = pd.DataFrame(
        {"fecha": [p.fecha for p in precios], "ticker": [p.ticker for p in precios], "close": [p.close for p in precios]}
    )
    largo["fecha"] = pd.to_datetime(largo["fecha"])
    ancho = largo.pivot_table(index="fecha", columns="ticker", values="close", aggfunc="last").sort_index()
    ancho.columns.name = None
    ancho.index.name = None
    return ancho, max(p.actualizado_en for p in precios)


def _matriz_vigente() -> pd.DataFrame:
    global _matriz, _leido_en, _actualizado_en, _error
    if _cargador is None:
        return _matriz
    if time.time() - _leido_en < settings.PRICE_CACHE_TTL_SECONDS:
        return _matriz
    try:
        _matriz, _actualizado_en = matriz_desde_precios(_cargador())
        _error = None
        logger.info("Almacén de precios leído: %d tickers, %d fechas.", _matriz.shape[1], _matriz.shape[0])
    except Exception as exc:  # noqa: BLE001 - sin almacén se sigue con Yahoo
        _error = f"{type(exc).__name__}: {exc}"[:300]
        logger.warning("No se pudo leer el almacén de precios: %s", exc)
    _leido_en = time.time()
    return _matriz


def serie(ticker: str, period: str) -> pd.DataFrame | None:
    """Historia del ticker en el almacén (DataFrame de una columna) si cubre
    el período pedido; None si no está o es más corta."""
    from core.data_providers import dias_periodo  # import local: evita el ciclo

    m = _matriz_vigente()
    if m.empty or ticker not in m.columns:
        return None
    s = m[ticker].dropna()
    if s.empty:
        return None
    dias = dias_periodo(period)
    if dias != float("inf"):
        inicio_pedido = pd.Timestamp.today().normalize() - pd.Timedelta(days=dias - MARGEN_COBERTURA_DIAS)
        if s.index.min() > inicio_pedido:
            return None
    return s.to_frame(ticker)


def estado() -> dict:
    m = _matriz_vigente()
    return {
        "configurado": _cargador is not None,
        "tickers": int(m.shape[1]),
        "ultima_fecha": m.index.max().date() if not m.empty else None,
        "actualizado_en": _actualizado_en,
        "error": _error,
    }
