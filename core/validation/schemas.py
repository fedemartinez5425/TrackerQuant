"""
Validaciones de negocio que van más allá de "el tipo de dato es correcto"
(eso ya lo hace Pydantic en models.py). Acá validamos reglas del dominio:
- ¿el ticker existe de verdad?
- ¿estoy vendiendo más de lo que tengo?
- ¿es una transacción duplicada?
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from core.storage.models import Transaction, TransactionAction


@dataclass
class ValidationResult:
    ok: bool
    errores: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.ok = False
        self.errores.append(msg)


def validar_ticker_existe(ticker: str, provider) -> ValidationResult:
    """Valida contra el data provider que el ticker efectivamente tenga precio."""
    result = ValidationResult(ok=True)
    try:
        precio = provider.get_price(ticker)
        if precio is None or precio <= 0:
            result.add(f"No se encontró precio válido para el ticker '{ticker}'.")
    except Exception as exc:  # noqa: BLE001
        result.add(f"No se pudo validar el ticker '{ticker}' contra el proveedor de datos: {exc}")
    return result


def validar_venta_no_supera_tenencia(
    transaccion: Transaction, transacciones_existentes: list[Transaction]
) -> ValidationResult:
    """Si es una venta, valida que no se venda más de lo que se tiene en cartera."""
    result = ValidationResult(ok=True)
    if transaccion.accion != TransactionAction.VENTA:
        return result

    tenencia = 0.0
    for t in transacciones_existentes:
        if t.ticker != transaccion.ticker:
            continue
        if t.accion == TransactionAction.COMPRA:
            tenencia += t.cantidad
        else:
            tenencia -= t.cantidad

    if transaccion.cantidad > tenencia:
        result.add(
            f"No podés vender {transaccion.cantidad} de {transaccion.ticker}: "
            f"solo tenés {tenencia} en cartera."
        )
    return result


def validar_no_duplicada(
    transaccion: Transaction, transacciones_existentes: list[Transaction]
) -> ValidationResult:
    """Chequeo simple anti-duplicado: mismo ticker, fecha, acción, cantidad y precio."""
    result = ValidationResult(ok=True)
    for t in transacciones_existentes:
        if (
            t.ticker == transaccion.ticker
            and t.fecha == transaccion.fecha
            and t.accion == transaccion.accion
            and t.cantidad == transaccion.cantidad
            and t.precio == transaccion.precio
        ):
            result.add(
                "Parece una transacción duplicada (mismo ticker, fecha, acción, "
                "cantidad y precio que otra ya cargada). Si es intencional, "
                "cambiá algún dato o confirmá igual desde 'Forzar carga'."
            )
            break
    return result


def validar_transaccion_completa(
    transaccion: Transaction,
    transacciones_existentes: list[Transaction],
    provider,
    forzar: bool = False,
    ticker_a_validar: str | None = None,
) -> ValidationResult:
    """Corre todas las validaciones de negocio sobre una transacción nueva.
    ticker_a_validar: qué ticker chequear contra el data provider -- el ADR
    para CEDEARs, o el ticker BCBA (con sufijo .BA) para acciones argentinas
    directas. Si no se pasa, usa el ticker BCBA de la transacción."""
    resultado = ValidationResult(ok=True)
    ticker_check = ticker_a_validar or transaccion.ticker

    for parcial in (
        validar_ticker_existe(ticker_check, provider),
        validar_venta_no_supera_tenencia(transaccion, transacciones_existentes),
    ):
        resultado.errores.extend(parcial.errores)
        if not parcial.ok:
            resultado.ok = False

    if not forzar:
        dup = validar_no_duplicada(transaccion, transacciones_existentes)
        resultado.errores.extend(dup.errores)
        if not dup.ok:
            resultado.ok = False

    return resultado
