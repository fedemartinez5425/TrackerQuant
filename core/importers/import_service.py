"""
Capa de aplicación entre "candidatos parseados de un CSV del broker" y
"filas guardadas en el repositorio". La usan tanto la importación manual
(pages/7_Importar_Broker.py) como la sincronización automática con Google
Drive (core/importers/drive_sync.py) -- una sola implementación, sin
duplicar la lógica de upsert de instrumentos + alta de transacciones.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.importers.broker_movimientos import MovimientoCandidato
from core.storage.base_repository import BaseRepository
from core.storage.models import AuditEvent, Currency, Instrumento, Transaction


@dataclass
class ResumenImportacion:
    importados: int = 0
    pendientes_de_ratio: list[str] = field(default_factory=list)  # tickers CEDEAR sin ratio
    errores: list[str] = field(default_factory=list)


def importar_candidatos(
    candidatos: list[MovimientoCandidato],
    repo: BaseRepository,
    usuario: str,
    ratios_override: dict[str, float] | None = None,
    origen: str = "broker",
) -> ResumenImportacion:
    """Para cada candidato: registra (o actualiza) su Instrumento en la tabla
    dimensión si hace falta, y da de alta la Transaction. Si es un CEDEAR sin
    ratio conocido (ni en el candidato ni en ratios_override), NO se importa
    esa fila -- se reporta en `pendientes_de_ratio` para que el usuario lo
    complete a mano una vez."""
    ratios_override = ratios_override or {}
    resumen = ResumenImportacion()
    instrumentos_ya_definidos = {i.ticker for i in repo.list_instrumentos()}

    for c in candidatos:
        ratio_final = ratios_override.get(c.ticker, c.ratio_cedear)

        if c.tipo_instrumento.value == "CEDEAR" and not ratio_final:
            resumen.pendientes_de_ratio.append(c.ticker)
            continue

        try:
            if c.ticker not in instrumentos_ya_definidos:
                repo.upsert_instrumento(
                    Instrumento(
                        ticker=c.ticker,
                        tipo_instrumento=c.tipo_instrumento,
                        ticker_usd=c.ticker_usd,
                        ratio_cedear=ratio_final,
                    )
                )
                instrumentos_ya_definidos.add(c.ticker)

            tx = Transaction(
                id_externo=c.id_externo,
                fecha=c.fecha,
                ticker=c.ticker,
                accion=c.accion,
                cantidad=c.cantidad,
                precio=c.precio,
                moneda=Currency(c.moneda) if c.moneda in ("ARS", "USD") else Currency.ARS,
                comision=c.comision,
                notas=f"Importado desde {origen}",
            )
            repo.add_transaction(tx)
            resumen.importados += 1
        except Exception as exc:  # noqa: BLE001
            resumen.errores.append(f"{c.ticker} ({c.id_externo}): {exc}")

    if resumen.importados or resumen.errores:
        repo.add_audit_event(
            AuditEvent(
                usuario=usuario,
                accion="IMPORTACION_BROKER",
                detalle=f"{resumen.importados} movimientos importados desde {origen}",
            )
        )
    return resumen
