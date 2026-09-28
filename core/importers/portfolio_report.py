"""
Parsea el "portfolio report" que exporta el broker (columnas:
instrumento;cantidad;precio;moneda;total) para poder reconciliarlo contra
lo que la app calcula a partir del log de transacciones.

Filas de efectivo (instrumento == "ARS" o "USD", sin ticker) se separan
del resto: son saldo disponible, no posiciones.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from core.importers.broker_movimientos import extraer_ticker_y_tipo, parsear_numero_ar
from core.storage.models import TipoInstrumento


@dataclass
class PosicionBroker:
    ticker: str
    tipo_instrumento: TipoInstrumento | None  # None si no se pudo determinar
    cantidad: float
    precio: float
    moneda: str
    total: float
    instrumento_original: str


@dataclass
class ResultadoPortfolioReport:
    posiciones: list[PosicionBroker]
    saldo_efectivo: dict[str, float]  # {"ARS": 134.27, "USD": 0.02}


def parsear_portfolio_report_csv(contenido_texto: str) -> ResultadoPortfolioReport:
    posiciones = []
    saldo_efectivo: dict[str, float] = {}

    lector = csv.DictReader(io.StringIO(contenido_texto), delimiter=";")
    for fila in lector:
        instrumento = (fila.get("instrumento") or "").strip()
        cantidad = parsear_numero_ar(fila.get("cantidad")) or 0.0
        precio = parsear_numero_ar(fila.get("precio")) or 0.0
        total = parsear_numero_ar(fila.get("total")) or 0.0
        moneda = (fila.get("moneda") or "ARS").strip()

        if instrumento.upper() in ("ARS", "USD"):
            saldo_efectivo[instrumento.upper()] = cantidad
            continue

        info = extraer_ticker_y_tipo(instrumento)
        ticker = info[0] if info else instrumento
        tipo = info[1] if info else None

        posiciones.append(
            PosicionBroker(
                ticker=ticker,
                tipo_instrumento=tipo,
                cantidad=cantidad,
                precio=precio,
                moneda=moneda,
                total=total,
                instrumento_original=instrumento,
            )
        )

    return ResultadoPortfolioReport(posiciones=posiciones, saldo_efectivo=saldo_efectivo)


def reconciliar(posiciones_broker: list[PosicionBroker], posiciones_app: list) -> list[dict]:
    """Compara cantidad por ticker entre lo que dice el broker y lo que la
    app calculó del log de transacciones. posiciones_app: list[Position]."""
    cantidades_app = {p.ticker: p.cantidad for p in posiciones_app}
    cantidades_broker = {p.ticker: p.cantidad for p in posiciones_broker}

    todos_los_tickers = set(cantidades_app) | set(cantidades_broker)
    filas = []
    for ticker in sorted(todos_los_tickers):
        cant_app = cantidades_app.get(ticker, 0.0)
        cant_broker = cantidades_broker.get(ticker, 0.0)
        diferencia = round(cant_app - cant_broker, 6)
        filas.append(
            {
                "Ticker": ticker,
                "Cantidad (app, desde transacciones)": cant_app,
                "Cantidad (broker)": cant_broker,
                "Diferencia": diferencia,
                "Coincide": "✅" if abs(diferencia) < 1e-6 else "⚠️",
            }
        )
    return filas
