"""
Importa el CSV de "movimientos de cuenta" que exportan los brokers argentinos
(columnas: nroTicket;nroComprobante;fechaEjecucion;...;instrumento;...;
cantidad;precio;...) y lo convierte en Transaction candidatas.

Solo se procesan filas de Compra/Venta de acciones/CEDEARs -- todo lo demás
(FCI, Recibo De Cobro, Orden De Pago, etc.) es movimiento de efectivo o de
otro tipo de activo que esta app no trackea, y se reporta como omitido en
vez de fallar.

Detección automática de CEDEAR vs. Acción Argentina directa: el broker
antepone "CEDEAR" al nombre cuando corresponde (ej. "CEDEAR AMAZON.COM,
INC (AMZN)"); si no lo antepone (ej. "PAMPA ENERGIA S.A. ... (PAMP)"), es
una acción argentina directa.

Idempotencia: cada fila trae un nroTicket único del broker, que se guarda
como Transaction.id_externo. Reimportar el mismo archivo (o uno que se
superponga en fechas) nunca duplica movimientos ya cargados.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from core.data_providers.comafi_ratios import obtener_ratio
from config.settings import settings
from core.storage.models import Currency, TipoInstrumento, TransactionAction

TIPOS_OPERACION_SOPORTADAS = {
    "Compra": TransactionAction.COMPRA,
    "Venta": TransactionAction.VENTA,
}


@dataclass
class MovimientoCandidato:
    id_externo: str
    fecha: date
    ticker: str
    tipo_instrumento: TipoInstrumento
    ticker_usd: str | None
    ratio_cedear: float | None  # None si es CEDEAR y no se encontró ratio -> hay que completarlo a mano
    accion: TransactionAction
    cantidad: float
    precio: float
    comision: float
    moneda: str = "ARS"


@dataclass
class ResultadoImportacion:
    candidatos: list[MovimientoCandidato] = field(default_factory=list)
    omitidos: list[dict] = field(default_factory=list)  # {fila, motivo}
    ya_importados: list[str] = field(default_factory=list)  # ids_externos que ya estaban en el log


def parsear_numero_ar(texto: str) -> float | None:
    """Convierte '1.234,56' (formato argentino) a 1234.56. '-2.378,80' -> -2378.80."""
    if texto is None:
        return None
    texto = texto.strip()
    if not texto:
        return None
    negativo = texto.startswith("-")
    texto = texto.lstrip("-").replace(".", "").replace(",", ".")
    try:
        valor = float(texto)
    except ValueError:
        return None
    return -valor if negativo else valor


def parsear_fecha_ar(texto: str) -> date | None:
    """Convierte 'dd-mm-yyyy' a date."""
    try:
        return datetime.strptime(texto.strip(), "%d-%m-%Y").date()
    except (ValueError, AttributeError):
        return None


def extraer_ticker_y_tipo(instrumento: str) -> tuple[str, TipoInstrumento] | None:
    """Extrae el ticker (del último grupo entre paréntesis) y determina si es
    CEDEAR (el broker antepone 'CEDEAR' al nombre) o Acción Argentina directa.
    Devuelve None para instrumentos que no son acciones/CEDEARs (FCI, etc.)."""
    if not instrumento or not instrumento.strip():
        return None
    if instrumento.strip().upper().startswith("FCI"):
        return None  # fondo común de inversión, no es una acción/CEDEAR

    grupos_parentesis = re.findall(r"\(([^)]+)\)", instrumento)
    if not grupos_parentesis:
        return None
    ticker = grupos_parentesis[-1].strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", ticker):
        return None  # no parece un ticker válido

    es_cedear = instrumento.strip().upper().startswith("CEDEAR")
    tipo = TipoInstrumento.CEDEAR if es_cedear else TipoInstrumento.ACCION_ARG
    return ticker, tipo


def parsear_movimientos_csv(
    contenido_texto: str, ids_externos_existentes: set[str] | None = None
) -> ResultadoImportacion:
    ids_existentes = ids_externos_existentes or set()
    resultado = ResultadoImportacion()

    lector = csv.DictReader(io.StringIO(contenido_texto), delimiter=";")
    for i, fila in enumerate(lector, start=2):  # +2: fila 1 es el header
        tipo_operacion = (fila.get("tipoOperacion") or "").strip()
        instrumento = (fila.get("instrumento") or "").strip()
        nro_ticket = (fila.get("nroTicket") or "").strip()

        if tipo_operacion not in TIPOS_OPERACION_SOPORTADAS:
            resultado.omitidos.append(
                {"fila": i, "motivo": f"Tipo de operación no soportado: '{tipo_operacion}' (no es Compra/Venta de un activo)"}
            )
            continue

        if nro_ticket and nro_ticket in ids_existentes:
            resultado.ya_importados.append(nro_ticket)
            continue

        info_instrumento = extraer_ticker_y_tipo(instrumento)
        if info_instrumento is None:
            resultado.omitidos.append(
                {"fila": i, "motivo": f"No se pudo identificar un ticker de acción/CEDEAR en '{instrumento}'"}
            )
            continue
        ticker, tipo_instrumento = info_instrumento

        fecha = parsear_fecha_ar(fila.get("fechaEjecucion") or fila.get("fechaLiquidacion"))
        cantidad = parsear_numero_ar(fila.get("cantidad"))
        precio = parsear_numero_ar(fila.get("precio"))
        comision = parsear_numero_ar(fila.get("comision")) or 0.0
        iva = parsear_numero_ar(fila.get("iva")) or 0.0
        otros = parsear_numero_ar(fila.get("otros")) or 0.0

        if fecha is None or cantidad is None or precio is None:
            resultado.omitidos.append({"fila": i, "motivo": "Fecha, cantidad o precio inválidos/vacíos"})
            continue

        ratio = None
        ticker_usd = None
        if tipo_instrumento == TipoInstrumento.CEDEAR:
            ticker_usd = ticker  # para la gran mayoría de CEDEARs, el símbolo coincide con el ADR
            ratio = obtener_ratio(ticker, settings.CEDEAR_RATIOS_FILE)

        resultado.candidatos.append(
            MovimientoCandidato(
                id_externo=nro_ticket,
                fecha=fecha,
                ticker=ticker,
                tipo_instrumento=tipo_instrumento,
                ticker_usd=ticker_usd,
                ratio_cedear=ratio,
                accion=TIPOS_OPERACION_SOPORTADAS[tipo_operacion],
                cantidad=abs(cantidad),
                precio=abs(precio),
                comision=abs(comision) + abs(iva) + abs(otros),
                moneda=(fila.get("moneda") or "ARS").strip() or "ARS",
            )
        )

    return resultado
