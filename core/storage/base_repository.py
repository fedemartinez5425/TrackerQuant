"""
Patrón repositorio: define el contrato que cualquier backend de storage
debe cumplir. El resto de la app programa contra esta interfaz, nunca
contra CSV o Google Sheets directamente.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.storage.models import AuditEvent, Instrumento, PortfolioForecast, PortfolioSnapshot, ProcessedFile, Transaction


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

    @abstractmethod
    def list_transactions(self) -> list[Transaction]: ...

    @abstractmethod
    def add_reversal(self, original_id: str, motivo: str, usuario: str) -> Transaction: ...

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
