"""
Motor de cartera: convierte la lista de transacciones en posiciones actuales.

Diseño relacional: cada transacción solo tiene un `ticker`. El tipo de
instrumento, el ADR y el ratio CEDEAR se buscan en la tabla dimensión
`instrumentos` (core/storage/models.py -- Instrumento), no se repiten en
cada fila de transacción. `instrumentos_por_ticker` se arma una vez
(get_repository().list_instrumentos()) y se pasa a estas funciones --
así siguen siendo puras y testeables sin tocar storage.

- ACCION_ARG: acción argentina comprada directamente en pesos (ej: PAMP,
  GGAL). Precio final = precio BCBA, sin ratio ni CCL.
- CEDEAR: instrumento extranjero comprado como CEDEAR (ej: AMZN). Precio
  final = precio BCBA si está disponible, si no el Precio Teórico
  (ADR en USD / ratio × CCL automático) como fallback.

Moneda: la cartera se valúa en pesos. Las transacciones cargadas en USD se
convierten a pesos con el CCL de SU fecha (no el de hoy) antes de sumar al
costo -- antes se sumaban dólares y pesos como si fueran lo mismo.

Reversos: las transacciones anuladas y sus reversos se excluyen por
completo (ver core/storage/models.transacciones_efectivas).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd

from core import data_providers
from core.data_providers.ccl_provider import ccl_en_fecha, get_ccl_automatico, get_ccl_historico
from core.storage.models import (
    Currency,
    Instrumento,
    TipoInstrumento,
    Transaction,
    TransactionAction,
    transacciones_efectivas,
)

logger = logging.getLogger(__name__)

TipoCambio = Callable[[date], "float | None"]  # fecha -> pesos por dólar


@dataclass
class Position:
    ticker: str
    tipo_instrumento: TipoInstrumento
    ticker_usd: str | None
    ratio_cedear: float | None
    cantidad: float
    costo_promedio: float
    valor_invertido: float
    precio_bcba: float | None
    precio_teorico: float | None
    precio_final: float | None
    prima_descuento: float | None
    valor_actual: float | None
    peso: float | None
    ganancia_perdida: float | None
    ganancia_perdida_pct: float | None


def _instrumento_o_default(ticker: str, instrumentos_por_ticker: dict[str, Instrumento]) -> Instrumento:
    """Si el ticker no está (todavía) en la tabla dimensión, se asume
    acción argentina directa por default -- nunca debería frenar el
    cálculo de la cartera por faltar metadata."""
    return instrumentos_por_ticker.get(ticker) or Instrumento(ticker=ticker, tipo_instrumento=TipoInstrumento.ACCION_ARG)


def tipo_cambio_ccl_historico() -> TipoCambio:
    """Función fecha -> CCL de esa fecha (serie histórica), con el CCL de hoy
    como respaldo. Se arma solo si hace falta (hay transacciones en USD)."""
    serie = get_ccl_historico("5y")
    actual = get_ccl_automatico()

    def _fx(fecha: date) -> float | None:
        valor = ccl_en_fecha(serie, fecha)
        if valor is None and actual:
            valor = actual["valor"]
        return valor

    return _fx


def calcular_tenencias(
    transactions: list[Transaction],
    instrumentos_por_ticker: dict[str, Instrumento] | None = None,
    fx_usd_ars: TipoCambio | None = None,
) -> dict[str, dict]:
    """Agrega transacciones por ticker: cantidad neta y costo promedio ponderado
    (en pesos). Usa costo promedio (no FIFO/LIFO) por simplicidad y transparencia.

    fx_usd_ars: tipo de cambio para convertir transacciones en USD a pesos a
    la fecha de cada una. Si hay transacciones en USD y no se pasa, se arma
    con el CCL histórico automáticamente."""
    instrumentos_por_ticker = instrumentos_por_ticker or {}
    efectivas = transacciones_efectivas(transactions)
    if fx_usd_ars is None and any(t.moneda == Currency.USD for t in efectivas):
        fx_usd_ars = tipo_cambio_ccl_historico()

    tenencias: dict[str, dict] = {}
    for t in sorted(efectivas, key=lambda x: (x.fecha, x.creado_en)):
        d = tenencias.setdefault(t.ticker, {"cantidad": 0.0, "costo_total": 0.0})
        factor = 1.0
        if t.moneda == Currency.USD:
            fx = fx_usd_ars(t.fecha) if fx_usd_ars else None
            if fx:
                factor = fx
            else:
                logger.warning("Sin CCL para convertir %s (%s, USD): se toma el precio sin convertir.", t.id, t.ticker)
        if t.accion == TransactionAction.COMPRA:
            d["cantidad"] += t.cantidad
            d["costo_total"] += (t.cantidad * t.precio + t.comision) * factor
        else:  # VENTA: reduce cantidad y costo proporcionalmente (costo promedio)
            if d["cantidad"] > 0:
                costo_promedio_actual = d["costo_total"] / d["cantidad"]
                d["costo_total"] -= t.cantidad * costo_promedio_actual
            d["cantidad"] -= t.cantidad

    return {k: v for k, v in tenencias.items() if v["cantidad"] > 1e-9}


def calcular_tenencias_a_fecha(
    transactions: list[Transaction], fecha_corte, instrumentos_por_ticker: dict[str, Instrumento] | None = None
) -> dict[str, dict]:
    """Igual que calcular_tenencias, pero solo considerando movimientos
    hasta una fecha de corte -- permite reconstruir cómo era la cartera
    en el pasado a partir del log completo de transacciones."""
    # Primero se resuelven los reversos sobre el log COMPLETO (un reverso
    # cargado después de la fecha de corte igual anula a la original).
    filtradas = [t for t in transacciones_efectivas(transactions) if t.fecha <= fecha_corte]
    return calcular_tenencias(filtradas, instrumentos_por_ticker)


def construir_cartera(
    transactions: list[Transaction], instrumentos_por_ticker: dict[str, Instrumento] | None = None
) -> list[Position]:
    instrumentos_por_ticker = instrumentos_por_ticker or {}
    tenencias = calcular_tenencias(transactions, instrumentos_por_ticker)
    return _tenencias_a_posiciones(tenencias, instrumentos_por_ticker)


def construir_cartera_a_fecha(
    transactions: list[Transaction], fecha_corte, instrumentos_por_ticker: dict[str, Instrumento] | None = None
) -> list[Position]:
    instrumentos_por_ticker = instrumentos_por_ticker or {}
    tenencias = calcular_tenencias_a_fecha(transactions, fecha_corte, instrumentos_por_ticker)
    return _tenencias_a_posiciones(tenencias, instrumentos_por_ticker)


def _tenencias_a_posiciones(tenencias: dict[str, dict], instrumentos_por_ticker: dict[str, Instrumento]) -> list[Position]:
    ccl_info = get_ccl_automatico()
    ccl_valor = ccl_info["valor"] if ccl_info else None

    provisional = []
    valor_total = 0.0

    for ticker, d in tenencias.items():
        inst = _instrumento_o_default(ticker, instrumentos_por_ticker)
        cantidad = d["cantidad"]
        costo_promedio = d["costo_total"] / cantidad if cantidad else 0.0

        precio_bcba = data_providers.get_price(f"{ticker}.BA")

        precio_teorico = None
        if inst.tipo_instrumento == TipoInstrumento.CEDEAR and inst.ratio_cedear and ccl_valor and inst.ticker_usd:
            precio_adr = data_providers.get_price(inst.ticker_usd)
            if precio_adr:
                precio_teorico = (precio_adr / inst.ratio_cedear) * ccl_valor

        precio_final = precio_bcba if precio_bcba is not None else precio_teorico

        prima_descuento = None
        if inst.tipo_instrumento == TipoInstrumento.CEDEAR and precio_bcba is not None and precio_teorico:
            prima_descuento = (precio_bcba - precio_teorico) / precio_teorico

        valor_actual = cantidad * precio_final if precio_final is not None else None
        if valor_actual is not None:
            valor_total += valor_actual

        provisional.append(
            {
                "ticker": ticker,
                "tipo_instrumento": inst.tipo_instrumento,
                "ticker_usd": inst.ticker_usd,
                "ratio_cedear": inst.ratio_cedear,
                "cantidad": cantidad,
                "costo_promedio": costo_promedio,
                "valor_invertido": d["costo_total"],
                "precio_bcba": precio_bcba,
                "precio_teorico": precio_teorico,
                "precio_final": precio_final,
                "prima_descuento": prima_descuento,
                "valor_actual": valor_actual,
            }
        )

    posiciones = []
    for p in provisional:
        peso = (p["valor_actual"] / valor_total) if (p["valor_actual"] and valor_total) else None
        gp = (p["valor_actual"] - p["valor_invertido"]) if p["valor_actual"] is not None else None
        gp_pct = (gp / p["valor_invertido"]) if (gp is not None and p["valor_invertido"]) else None
        posiciones.append(Position(peso=peso, ganancia_perdida=gp, ganancia_perdida_pct=gp_pct, **p))
    return sorted(posiciones, key=lambda x: (x.valor_actual or 0), reverse=True)


def cartera_a_dataframe(posiciones: list[Position]) -> pd.DataFrame:
    columnas = [
        "Ticker", "Tipo", "Cantidad", "Costo Promedio", "Precio BCBA", "Precio Teórico (CCL)",
        "Precio Final", "Prima/Desc. %", "Valor Actual", "Valor Invertido",
        "Peso %", "G/P $", "G/P %",
    ]
    if not posiciones:
        return pd.DataFrame(columns=columnas)
    rows = [
        {
            "Ticker": p.ticker,
            "Tipo": "CEDEAR" if p.tipo_instrumento == TipoInstrumento.CEDEAR else "Acción ARG",
            "Cantidad": p.cantidad,
            "Costo Promedio": p.costo_promedio,
            "Precio BCBA": p.precio_bcba,
            "Precio Teórico (CCL)": p.precio_teorico,
            "Precio Final": p.precio_final,
            "Prima/Desc. %": p.prima_descuento,
            "Valor Actual": p.valor_actual,
            "Valor Invertido": p.valor_invertido,
            "Peso %": p.peso,
            "G/P $": p.ganancia_perdida,
            "G/P %": p.ganancia_perdida_pct,
        }
        for p in posiciones
    ]
    return pd.DataFrame(rows)


def resumen_cartera(posiciones: list[Position]) -> dict:
    valor_actual_total = sum(p.valor_actual or 0 for p in posiciones)
    valor_invertido_total = sum(p.valor_invertido for p in posiciones)
    gp_total = valor_actual_total - valor_invertido_total
    gp_pct_total = (gp_total / valor_invertido_total) if valor_invertido_total else None
    return {
        "valor_actual_total": valor_actual_total,
        "valor_invertido_total": valor_invertido_total,
        "ganancia_perdida_total": gp_total,
        "ganancia_perdida_pct_total": gp_pct_total,
        "cantidad_posiciones": len(posiciones),
    }
