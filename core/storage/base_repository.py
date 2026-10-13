"""
Patrón repositorio: define el contrato que cualquier backend de storage
debe cumplir. El resto de la app programa contra esta interfaz, nunca
contra CSV o Google Sheets directamente.

La lógica que NO depende del backend (reversos, alta en lote por defecto)
vive acá una sola vez, en vez de estar duplicada en cada implementación.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from core.storage.models import (
    REVERSO_PREFIJO,
    AuditEvent,
    Instrumento,
    PortfolioForecast,
    PortfolioSnapshot,
    ProcessedFile,
    Transaction,
    TransactionAction,
    ids_reversados,
)


class BaseRepository(ABC):
    # --- Instrumentos (tabla dimensión) ---
    @abstractmethod
    def upsert_instrumento(self, instrumento: Instrumento) -> None: ...

    @abstractmethod
    def get_instrumento(self, ticker: str) -> Instrumento | None: ...

    @abstractmethod
    def list_instrumentos(self) -> list[Instrumento]: ...

    # --- Transacciones (tabla de hechos, append-only) ---
    @abstractmethod
    def add_transaction(self, transaction: Transaction) -> None: ...

    def add_transactions(self, transactions: list[Transaction]) -> None:
        """Alta en lote. Por defecto, una por una; los backends remotos
        (Google Sheets) lo sobreescriben con una sola llamada a la API."""
        for t in transactions:
            self.add_transaction(t)

    @abstractmethod
    def list_transactions(self) -> list[Transaction]: ...

    def add_reversal(self, original_id: str, motivo: str, usuario: str) -> Transaction:
        """Nunca se borra ni edita una transacción: se agrega un reverso que
        la ANULA (ver models.transacciones_efectivas). Ambas quedan en el
        historial; ninguna de las dos afecta la cartera."""
        transacciones = self.list_transactions()
        originales = [t for t in transacciones if t.id == original_id]
        if not originales:
            raise ValueError(f"No existe la transacción {original_id}")
        original = originales[0]
        if original.revierte_a:
            raise ValueError(f"{original_id} ya es un reverso: no se puede reversar un reverso.")
        if original_id in ids_reversados(transacciones):
            raise ValueError(f"La transacción {original_id} ya fue reversada.")

        accion_inversa = (
            TransactionAction.VENTA if original.accion == TransactionAction.COMPRA else TransactionAction.COMPRA
        )
        reverso = Transaction(
            fecha=date.today(),
            ticker=original.ticker,
            accion=accion_inversa,
            cantidad=original.cantidad,
            precio=original.precio,
            moneda=original.moneda,
            comision=0.0,
            notas=f"{REVERSO_PREFIJO}{original_id} — motivo: {motivo}",
        )
        self.add_transaction(reverso)
        self.add_audit_event(
            AuditEvent(usuario=usuario, accion="REVERSO_TRANSACCION", detalle=f"Reversó {original_id} ({motivo})")
        )
        return reverso

    # --- Snapshots históricos (para analytics) ---
    @abstractmethod
    def add_snapshot(self, snapshot: PortfolioSnapshot) -> None: ...

    @abstractmethod
    def list_snapshots(self) -> list[PortfolioSnapshot]: ...

    # --- Forecasts emitidos (para backtest de precisión) ---
    @abstractmethod
    def add_forecast(self, forecast: PortfolioForecast) -> None: ...

    @abstractmethod
    def list_forecasts(self) -> list[PortfolioForecast]: ...

    # --- Archivos de Drive ya procesados (idempotencia de la sincronización) ---
    @abstractmethod
    def add_processed_file(self, processed: ProcessedFile) -> None: ...

    @abstractmethod
    def list_processed_file_ids(self) -> set[str]: ...

    # --- Auditoría ---
    @abstractmethod
    def add_audit_event(self, event: AuditEvent) -> None: ...

    @abstractmethod
    def list_audit_events(self, limit: int = 200) -> list[AuditEvent]: ...
