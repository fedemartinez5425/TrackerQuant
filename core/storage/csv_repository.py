"""
Backend de storage por defecto: archivos CSV locales en /data.
No requiere ninguna cuenta ni credencial externa -> la app corre
"out of the box" con `streamlit run app.py` mientras no configurás
Google Sheets.

⚠️ En Streamlit Community Cloud el filesystem es efímero (se resetea en
cada redeploy/reinicio) -- este backend es solo para desarrollo local.
En producción usar STORAGE_BACKEND=gsheets (ver sheets_repository.py).

Mismo contrato que SheetsRepository, así que pasar a Google Sheets no
rompe nada del resto del sistema.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from core.storage.base_repository import BaseRepository
from core.storage.models import (
    AuditEvent,
    Instrumento,
    PortfolioForecast,
    PortfolioSnapshot,
    ProcessedFile,
    Transaction,
    WatchlistItem,
)

logger = logging.getLogger(__name__)

INSTRUMENTO_FIELDS = ["ticker", "tipo_instrumento", "ticker_usd", "ratio_cedear", "nombre", "actualizado_en"]
TRANSACTION_FIELDS = [
    "id", "id_externo", "fecha", "ticker", "accion",
    "cantidad", "precio", "moneda", "comision", "notas", "creado_en",
]
AUDIT_FIELDS = ["id", "timestamp", "usuario", "accion", "detalle"]
SNAPSHOT_FIELDS = [
    "id", "fecha", "valor_total_usd", "cantidad_posiciones", "volatilidad_anualizada",
    "var_95_pct", "beta_vs_benchmark", "correlacion_promedio", "composicion_json", "creado_en",
]
FORECAST_FIELDS = ["id", "fecha", "horizonte_dias", "vol_pronosticada_anual", "metodo", "composicion_json", "creado_en"]
PROCESSED_FILE_FIELDS = ["id", "drive_file_id", "nombre_archivo", "tipo_detectado", "filas_importadas", "procesado_en"]
WATCHLIST_FIELDS = ["ticker", "tipo_instrumento", "ticker_usd", "ratio_cedear", "notas", "agregado_en"]


def _ensure_file(path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()


class CsvRepository(BaseRepository):
    def __init__(
        self,
        transactions_file: Path,
        audit_file: Path,
        snapshots_file: Path,
        instrumentos_file: Path,
        processed_files_file: Path,
        forecasts_file: Path,
        watchlist_file: Path | None = None,
    ):
        self.transactions_file = transactions_file
        self.audit_file = audit_file
        self.snapshots_file = snapshots_file
        self.instrumentos_file = instrumentos_file
        self.processed_files_file = processed_files_file
        self.forecasts_file = forecasts_file
        self.watchlist_file = watchlist_file or transactions_file.parent / "watchlist.csv"
        _ensure_file(self.transactions_file, TRANSACTION_FIELDS)
        _ensure_file(self.audit_file, AUDIT_FIELDS)
        _ensure_file(self.snapshots_file, SNAPSHOT_FIELDS)
        _ensure_file(self.instrumentos_file, INSTRUMENTO_FIELDS)
        _ensure_file(self.processed_files_file, PROCESSED_FILE_FIELDS)
        _ensure_file(self.forecasts_file, FORECAST_FIELDS)
        _ensure_file(self.watchlist_file, WATCHLIST_FIELDS)

    # ---------------- helpers ----------------
    @staticmethod
    def _leer(path: Path, campo_clave: str = "id") -> list[dict]:
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as f:
            return [row for row in csv.DictReader(f) if row.get(campo_clave)]

    @staticmethod
    def _agregar(path: Path, fields: list[str], filas: list[dict]) -> None:
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            for fila in filas:
                writer.writerow(fila)

    # ---------------- Instrumentos ----------------
    def upsert_instrumento(self, instrumento: Instrumento) -> None:
        existentes = self.list_instrumentos()
        actualizado = False
        for i, inst in enumerate(existentes):
            if inst.ticker == instrumento.ticker:
                existentes[i] = instrumento
                actualizado = True
                break
        if not actualizado:
            existentes.append(instrumento)

        with self.instrumentos_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=INSTRUMENTO_FIELDS)
            writer.writeheader()
            for inst in existentes:
                writer.writerow(inst.to_row())

    def get_instrumento(self, ticker: str) -> Instrumento | None:
        for inst in self.list_instrumentos():
            if inst.ticker == ticker.upper().strip():
                return inst
        return None

    def list_instrumentos(self) -> list[Instrumento]:
        return [Instrumento.from_row(r) for r in self._leer(self.instrumentos_file, "ticker")]

    # ---------------- Transacciones ----------------
    def add_transaction(self, transaction: Transaction) -> None:
        self.add_transactions([transaction])

    def add_transactions(self, transactions: list[Transaction]) -> None:
        if not transactions:
            return
        self._agregar(self.transactions_file, TRANSACTION_FIELDS, [t.to_row() for t in transactions])
        logger.info("%d transacción(es) agregada(s).", len(transactions))

    def list_transactions(self) -> list[Transaction]:
        return [Transaction.from_row(r) for r in self._leer(self.transactions_file)]

    # ---------------- Snapshots ----------------
    def add_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self._agregar(self.snapshots_file, SNAPSHOT_FIELDS, [snapshot.to_row()])

    def list_snapshots(self) -> list[PortfolioSnapshot]:
        out = [PortfolioSnapshot.from_row(r) for r in self._leer(self.snapshots_file)]
        return sorted(out, key=lambda s: s.fecha)

    # ---------------- Forecasts ----------------
    def add_forecast(self, forecast: PortfolioForecast) -> None:
        self._agregar(self.forecasts_file, FORECAST_FIELDS, [forecast.to_row()])

    def list_forecasts(self) -> list[PortfolioForecast]:
        out = [PortfolioForecast.from_row(r) for r in self._leer(self.forecasts_file)]
        return sorted(out, key=lambda f: f.fecha, reverse=True)

    # ---------------- Archivos procesados (Drive sync) ----------------
    def add_processed_file(self, processed: ProcessedFile) -> None:
        self._agregar(self.processed_files_file, PROCESSED_FILE_FIELDS, [processed.to_row()])

    def list_processed_file_ids(self) -> set[str]:
        return {r["drive_file_id"] for r in self._leer(self.processed_files_file, "drive_file_id")}

    # ---------------- Watchlist ----------------
    def _escribir_watchlist(self, items: list[WatchlistItem]) -> None:
        with self.watchlist_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=WATCHLIST_FIELDS)
            writer.writeheader()
            for item in items:
                writer.writerow(item.to_row())

    def upsert_watchlist_item(self, item: WatchlistItem) -> None:
        items = [i for i in self.list_watchlist() if i.ticker != item.ticker]
        self._escribir_watchlist(items + [item])

    def list_watchlist(self) -> list[WatchlistItem]:
        return [WatchlistItem.from_row(r) for r in self._leer(self.watchlist_file, "ticker")]

    def remove_watchlist_item(self, ticker: str) -> bool:
        ticker = ticker.upper().strip()
        items = self.list_watchlist()
        quedan = [i for i in items if i.ticker != ticker]
        if len(quedan) == len(items):
            return False
        self._escribir_watchlist(quedan)
        return True

    # ---------------- Auditoría ----------------
    def add_audit_event(self, event: AuditEvent) -> None:
        self._agregar(self.audit_file, AUDIT_FIELDS, [event.to_row()])

    def list_audit_events(self, limit: int = 200) -> list[AuditEvent]:
        out = [AuditEvent.from_row(r) for r in self._leer(self.audit_file)]
        return sorted(out, key=lambda e: e.timestamp, reverse=True)[:limit]
