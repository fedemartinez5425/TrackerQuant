"""
Backend de storage principal para producción: Google Sheets vía gspread +
service account. Mismo contrato (BaseRepository) que CsvRepository.

Diseño relacional (5 pestañas = 5 tablas):
- instrumentos: dimensión (ticker, tipo, ADR, ratio) -- 1 fila por ticker
- transactions: hechos, append-only, referencia ticker
- portfolio_snapshots: hechos, append-only, para analytics histórico
- processed_files: registro de qué archivos de Drive ya se importaron
- audit_log: quién hizo qué y cuándo

Credenciales: en local, un archivo JSON de service account
(GOOGLE_SERVICE_ACCOUNT_FILE). En Streamlit Cloud, el mismo JSON pero
pegado en st.secrets (ver core/storage/__init__.py), nunca commiteado al repo.

Cuota de la API: Google Sheets permite ~60 lecturas por minuto por usuario.
Antes cada rerun de Streamlit hacía ~4 llamadas (buscar la pestaña + leer
todo) y era fácil recibir errores 429. Ahora:
- los objetos Worksheet se resuelven UNA vez (no se vuelve a pedir metadata);
- cada pestaña leída se cachea en memoria CACHE_TTL_SEGUNDOS, y cualquier
  escritura de esta app sobre esa pestaña invalida su cache al instante;
- las altas en lote usan append_rows (una sola llamada).
"""
from __future__ import annotations

import logging
import time

from core.storage.base_repository import BaseRepository
from core.storage.csv_repository import (
    AUDIT_FIELDS,
    FORECAST_FIELDS,
    INSTRUMENTO_FIELDS,
    PROCESSED_FILE_FIELDS,
    SNAPSHOT_FIELDS,
    TRANSACTION_FIELDS,
)
from core.storage.models import (
    AuditEvent,
    Instrumento,
    PortfolioForecast,
    PortfolioSnapshot,
    ProcessedFile,
    Transaction,
)

logger = logging.getLogger(__name__)

SHEET_INSTRUMENTOS = "instrumentos"
SHEET_TRANSACTIONS = "transactions"
SHEET_AUDIT = "audit_log"
SHEET_SNAPSHOTS = "portfolio_snapshots"
SHEET_FORECASTS = "forecast_log"
SHEET_PROCESSED_FILES = "processed_files"

CACHE_TTL_SEGUNDOS = 60


def _celdas(row: dict, fields: list[str]) -> list[str]:
    return ["" if row.get(f) is None else str(row.get(f)) for f in fields]


class SheetsRepository(BaseRepository):
    def __init__(self, spreadsheet_id: str, credentials_info: dict | None, service_account_file: str | None):
        import gspread  # import local: dependencia opcional
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        if credentials_info:
            creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
        self._worksheets: dict = {}
        self._cache_filas: dict[str, tuple[float, list[str], list[list[str]]]] = {}

        existentes = {ws.title: ws for ws in self.spreadsheet.worksheets()}  # 1 sola llamada
        for titulo, headers in (
            (SHEET_INSTRUMENTOS, INSTRUMENTO_FIELDS),
            (SHEET_TRANSACTIONS, TRANSACTION_FIELDS),
            (SHEET_AUDIT, AUDIT_FIELDS),
            (SHEET_SNAPSHOTS, SNAPSHOT_FIELDS),
            (SHEET_FORECASTS, FORECAST_FIELDS),
            (SHEET_PROCESSED_FILES, PROCESSED_FILE_FIELDS),
        ):
            ws = existentes.get(titulo)
            if ws is None:
                ws = self.spreadsheet.add_worksheet(title=titulo, rows=2000, cols=len(headers) + 2)
                ws.append_row(headers)
            self._worksheets[titulo] = ws

    # ---------------- helpers ----------------
    def _worksheet(self, title: str):
        return self._worksheets[title]

    def _invalidar(self, title: str) -> None:
        self._cache_filas.pop(title, None)

    def invalidar_cache(self) -> None:
        """Fuerza a releer todo de Sheets (ej. si editaste la planilla a mano)."""
        self._cache_filas.clear()

    @staticmethod
    def _row_to_dict(headers: list[str], row: list[str]) -> dict:
        return {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}

    def _all_rows(self, title: str) -> tuple[list[str], list[list[str]]]:
        ahora = time.time()
        cacheado = self._cache_filas.get(title)
        if cacheado and ahora - cacheado[0] < CACHE_TTL_SEGUNDOS:
            return cacheado[1], cacheado[2]
        values = self._worksheet(title).get_all_values()
        headers, rows = (values[0], values[1:]) if len(values) >= 2 else ((values[0] if values else []), [])
        self._cache_filas[title] = (ahora, headers, rows)
        return headers, rows

    def _dicts(self, title: str, campo_clave: str = "id") -> list[dict]:
        headers, rows = self._all_rows(title)
        out = []
        for r in rows:
            d = self._row_to_dict(headers, r)
            if d.get(campo_clave):
                out.append(d)
        return out

    def _append(self, title: str, fields: list[str], filas: list[dict]) -> None:
        if not filas:
            return
        ws = self._worksheet(title)
        if len(filas) == 1:
            ws.append_row(_celdas(filas[0], fields))
        else:
            ws.append_rows([_celdas(f, fields) for f in filas])
        self._invalidar(title)

    # ---------------- Instrumentos ----------------
    def upsert_instrumento(self, instrumento: Instrumento) -> None:
        from gspread.utils import rowcol_to_a1

        ws = self._worksheet(SHEET_INSTRUMENTOS)
        self._invalidar(SHEET_INSTRUMENTOS)  # leer fresco antes de decidir update vs append
        headers, rows = self._all_rows(SHEET_INSTRUMENTOS)
        nueva_fila = _celdas(instrumento.to_row(), INSTRUMENTO_FIELDS)

        for i, r in enumerate(rows, start=2):  # +2: fila 1 es header, gspread es 1-indexed
            d = self._row_to_dict(headers, r)
            if d.get("ticker") == instrumento.ticker:
                rango = f"A{i}:{rowcol_to_a1(i, len(INSTRUMENTO_FIELDS))}"
                ws.update(range_name=rango, values=[nueva_fila])
                self._invalidar(SHEET_INSTRUMENTOS)
                return
        self._append(SHEET_INSTRUMENTOS, INSTRUMENTO_FIELDS, [instrumento.to_row()])

    def get_instrumento(self, ticker: str) -> Instrumento | None:
        for inst in self.list_instrumentos():
            if inst.ticker == ticker.upper().strip():
                return inst
        return None

    def list_instrumentos(self) -> list[Instrumento]:
        return [Instrumento.from_row(d) for d in self._dicts(SHEET_INSTRUMENTOS, "ticker")]

    # ---------------- Transacciones ----------------
    def add_transaction(self, transaction: Transaction) -> None:
        self.add_transactions([transaction])

    def add_transactions(self, transactions: list[Transaction]) -> None:
        self._append(SHEET_TRANSACTIONS, TRANSACTION_FIELDS, [t.to_row() for t in transactions])

    def list_transactions(self) -> list[Transaction]:
        return [Transaction.from_row(d) for d in self._dicts(SHEET_TRANSACTIONS)]

    # ---------------- Snapshots ----------------
    def add_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self._append(SHEET_SNAPSHOTS, SNAPSHOT_FIELDS, [snapshot.to_row()])

    def list_snapshots(self) -> list[PortfolioSnapshot]:
        out = [PortfolioSnapshot.from_row(d) for d in self._dicts(SHEET_SNAPSHOTS)]
        return sorted(out, key=lambda s: s.fecha)

    # ---------------- Forecasts ----------------
    def add_forecast(self, forecast: PortfolioForecast) -> None:
        self._append(SHEET_FORECASTS, FORECAST_FIELDS, [forecast.to_row()])

    def list_forecasts(self) -> list[PortfolioForecast]:
        out = [PortfolioForecast.from_row(d) for d in self._dicts(SHEET_FORECASTS)]
        return sorted(out, key=lambda f: f.fecha, reverse=True)

    # ---------------- Archivos procesados (Drive sync) ----------------
    def add_processed_file(self, processed: ProcessedFile) -> None:
        self._append(SHEET_PROCESSED_FILES, PROCESSED_FILE_FIELDS, [processed.to_row()])

    def list_processed_file_ids(self) -> set[str]:
        return {d["drive_file_id"] for d in self._dicts(SHEET_PROCESSED_FILES, "drive_file_id")}

    # ---------------- Auditoría ----------------
    def add_audit_event(self, event: AuditEvent) -> None:
        self._append(SHEET_AUDIT, AUDIT_FIELDS, [event.to_row()])

    def list_audit_events(self, limit: int = 200) -> list[AuditEvent]:
        out = [AuditEvent.from_row(d) for d in self._dicts(SHEET_AUDIT)]
        return sorted(out, key=lambda e: e.timestamp, reverse=True)[:limit]
