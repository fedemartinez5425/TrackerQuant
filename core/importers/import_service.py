"""
Capa de aplicación entre "candidatos parseados de un CSV del broker" y
"filas guardadas en el repositorio". La usan tanto la importación manual
(pages/7_Importar_Broker.py) como la sincronización automática con Google
Drive (pages/8_Configuracion.py) -- una sola implementación, sin duplicar
la lógica de upsert de instrumentos + alta de transacciones.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.importers.broker_movimientos import MovimientoCandidato
from core.storage.base_repository import BaseRepository
from core.storage.models import AuditEvent, Currency, Instrumento, TipoInstrumento, Transaction


@dataclass
class ResumenImportacion:
    importados: int = 0
    pendientes_de_ratio: list[str] = field(default_factory=list)  # tickers CEDEAR sin ratio
    errores: list[str] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        """True si no quedó nada sin importar (ni por falta de ratio ni por error)."""
        return not self.pendientes_de_ratio and not self.errores


def importar_candidatos(
    candidatos: list[MovimientoCandidato],
    repo: BaseRepository,
    usuario: str,
    ratios_override: dict[str, float] | None = None,
    origen: str = "broker",
) -> ResumenImportacion:
    """Para cada candidato: registra su Instrumento en la tabla dimensión si
    todavía no existe, y da de alta la Transaction.

    Ratio de un CEDEAR, en orden de prioridad: el que el usuario completó a
    mano (ratios_override) > el ya registrado en `instrumentos` > el del
    cache de Comafi. Si no hay ninguno, esa fila NO se importa y se reporta en
    `pendientes_de_ratio` para completarlo una vez.

    Las transacciones válidas se guardan todas juntas al final (una sola
    llamada a la API en Google Sheets, en vez de una por fila)."""
    ratios_override = ratios_override or {}
    resumen = ResumenImportacion()
    instrumentos_definidos = {i.ticker: i for i in repo.list_instrumentos()}
    a_guardar: list[Transaction] = []

    for c in candidatos:
        existente = instrumentos_definidos.get(c.ticker)
        ratio_final = ratios_override.get(c.ticker) or (existente.ratio_cedear if existente else None) or c.ratio_cedear

        es_cedear = (existente.tipo_instrumento if existente else c.tipo_instrumento) == TipoInstrumento.CEDEAR
        if es_cedear and not ratio_final:
            if c.ticker not in resumen.pendientes_de_ratio:
                resumen.pendientes_de_ratio.append(c.ticker)
            continue

        try:
            if existente is None:
                inst = Instrumento(
                    ticker=c.ticker,
                    tipo_instrumento=c.tipo_instrumento,
                    ticker_usd=c.ticker_usd,
                    ratio_cedear=ratio_final if c.tipo_instrumento == TipoInstrumento.CEDEAR else None,
                )
                repo.upsert_instrumento(inst)
                instrumentos_definidos[c.ticker] = inst

            a_guardar.append(
                Transaction(
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
            )
        except Exception as exc:  # noqa: BLE001
            resumen.errores.append(f"{c.ticker} ({c.id_externo}): {exc}")

    if a_guardar:
        try:
            repo.add_transactions(a_guardar)
            resumen.importados = len(a_guardar)
        except Exception as exc:  # noqa: BLE001
            resumen.errores.append(f"No se pudieron guardar {len(a_guardar)} movimientos: {exc}")

    if resumen.importados or resumen.errores:
        repo.add_audit_event(
            AuditEvent(
                usuario=usuario,
                accion="IMPORTACION_BROKER",
                detalle=f"{resumen.importados} movimientos importados desde {origen}"
                + (f" ({len(resumen.errores)} con error)" if resumen.errores else ""),
            )
        )
    return resumen
