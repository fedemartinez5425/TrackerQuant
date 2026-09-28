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
pegado en st.secrets (ver config/settings.py -> get_google_credentials_info()),
nunca commiteado al repo.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

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
    TransactionAction,
    TipoInstrumento,
)

logger = logging.getLogger(__name__)

SHEET_INSTRUMENTOS = "instrumentos"
SHEET_TRANSACTIONS = "transactions"
SHEET_AUDIT = "audit_log"
SHEET_SNAPSHOTS = "portfolio_snapshots"
SHEET_FORECASTS = "forecast_log"
SHEET_PROCESSED_FILES = "processed_files"


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
        self._ensure_worksheet(SHEET_INSTRUMENTOS, INSTRUMENTO_FIELDS)
        self._ensure_worksheet(SHEET_TRANSACTIONS, TRANSACTION_FIELDS)
        self._ensure_worksheet(SHEET_AUDIT, AUDIT_FIELDS)
        self._ensure_worksheet(SHEET_SNAPSHOTS, SNAPSHOT_FIELDS)
        self._ensure_worksheet(SHEET_FORECASTS, FORECAST_FIELDS)
        self._ensure_worksheet(SHEET_PROCESSED_FILES, PROCESSED_FILE_FIELDS)

    def _ensure_worksheet(self, title: str, headers: list[str]):
        try:
            ws = self.spreadsheet.worksheet(title)
        except Exception:  # noqa: BLE001 - gspread.WorksheetNotFound
            ws = self.spreadsheet.add_worksheet(title=title, rows=2000, cols=len(headers) + 2)
            ws.append_row(headers)
        return ws

    def _worksheet(self, title: str):
        return self.spreadsheet.worksheet(title)

    @staticmethod
    def _row_to_dict(headers: list[str], row: list[str]) -> dict:
        return {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}

    def _all_rows(self, title: str) -> tuple[list[str], list[list[str]]]:
        values = self.spreadsheet.worksheet(title).get_all_values()
        if len(values) < 2:
            return [], []
        return values[0], values[1:]

    # ---------------- Instrumentos ----------------
    def upsert_instrumento(self, instrumento: Instrumento) -> None:
        ws = self._worksheet(SHEET_INSTRUMENTOS)
        headers, rows = self._all_rows(SHEET_INSTRUMENTOS)
        row_dict = instrumento.to_row()
        nueva_fila = [str(row_dict.get(f, "") if row_dict.get(f) is not None else "") for f in INSTRUMENTO_FIELDS]

        for i, r in enumerate(rows, start=2):  # +2: fila 1 es header, gspread es 1-indexed
            d = self._row_to_dict(headers, r)
            if d.get("ticker") == instrumento.ticker:
                ws.update(f"A{i}:{chr(64 + len(INSTRUMENTO_FIELDS))}{i}", [nueva_fila])
                return
        ws.append_row(nueva_fila)

    def get_instrumento(self, ticker: str) -> Instrumento | None:
        for inst in self.list_instrumentos():
            if inst.ticker == ticker.upper().strip():
                return inst
        return None

    def list_instrumentos(self) -> list[Instrumento]:
        headers, rows = self._all_rows(SHEET_INSTRUMENTOS)
        out = []
        for r in rows:
            d = self._row_to_dict(headers, r)
            if not d.get("ticker"):
                continue
            out.append(
                Instrumento(
                    ticker=d["ticker"],
                    tipo_instrumento=TipoInstrumento(d.get("tipo_instrumento") or "ACCION_ARG"),
                    ticker_usd=d.get("ticker_usd") or None,
                    ratio_cedear=float(d["ratio_cedear"]) if d.get("ratio_cedear") else None,
                    nombre=d.get("nombre", ""),
                    actualizado_en=datetime.fromisoformat(d["actualizado_en"]),
                )
            )
        return out

    # ---------------- Transacciones ----------------
    def add_transaction(self, transaction: Transaction) -> None:
        ws = self._worksheet(SHEET_TRANSACTIONS)
        row = transaction.to_row()
        ws.append_row([str(row.get(f, "") if row.get(f) is not None else "") for f in TRANSACTION_FIELDS])

    def list_transactions(self) -> list[Transaction]:
        headers, rows = self._all_rows(SHEET_TRANSACTIONS)
        out = []
        for r in rows:
            d = self._row_to_dict(headers, r)
            if not d.get("id"):
                continue
            out.append(
                Transaction(
                    id=d["id"],
                    id_externo=d.get("id_externo") or None,
                    fecha=date.fromisoformat(d["fecha"]),
                    ticker=d["ticker"],
                    accion=TransactionAction(d["accion"]),
                    cantidad=float(d["cantidad"]),
                    precio=float(d["precio"]),
                    moneda=d.get("moneda", "ARS"),
                    comision=float(d.get("comision") or 0.0),
                    notas=d.get("notas", ""),
                    creado_en=datetime.fromisoformat(d["creado_en"]),
                )
            )
        return out

    def add_reversal(self, original_id: str, motivo: str, usuario: str) -> Transaction:
        originales = [t for t in self.list_transactions() if t.id == original_id]
        if not originales:
            raise ValueError(f"No existe la transacción {original_id}")
        original = originales[0]
        accion_inversa = (
            TransactionAction.VENTA
            if original.accion == TransactionAction.COMPRA
            else TransactionAction.COMPRA
        )
        reverso = Transaction(
            fecha=date.today(),
            ticker=original.ticker,
            accion=accion_inversa,
            cantidad=original.cantidad,
            precio=original.precio,
            moneda=original.moneda,
            comision=0.0,
            notas=f"REVERSO de {original_id} — motivo: {motivo}",
        )
        self.add_transaction(reverso)
        self.add_audit_event(
            AuditEvent(usuario=usuario, accion="REVERSO_TRANSACCION", detalle=f"Reversó {original_id} ({motivo})")
        )
        return reverso

    # ---------------- Snapshots ----------------
    def add_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        ws = self._worksheet(SHEET_SNAPSHOTS)
        row = snapshot.to_row()
        ws.append_row([str(row.get(f, "") if row.get(f) is not None else "") for f in SNAPSHOT_FIELDS])

    def list_snapshots(self) -> list[PortfolioSnapshot]:
        headers, rows = self._all_rows(SHEET_SNAPSHOTS)
        out = []
        for r in rows:
            d = self._row_to_dict(headers, r)
            if not d.get("id"):
                continue
            out.append(
                PortfolioSnapshot(
                    id=d["id"],
                    fecha=date.fromisoformat(d["fecha"]),
                    valor_total_usd=float(d["valor_total_usd"]),
                    cantidad_posiciones=int(d["cantidad_posiciones"]),
                    volatilidad_anualizada=float(d["volatilidad_anualizada"]) if d.get("volatilidad_anualizada") else None,
                    var_95_pct=float(d["var_95_pct"]) if d.get("var_95_pct") else None,
                    beta_vs_benchmark=float(d["beta_vs_benchmark"]) if d.get("beta_vs_benchmark") else None,
                    correlacion_promedio=float(d["correlacion_promedio"]) if d.get("correlacion_promedio") else None,
                    composicion_json=d.get("composicion_json", ""),
                    creado_en=datetime.fromisoformat(d["creado_en"]),
                )
            )
        return sorted(out, key=lambda s: s.fecha)

    # ---------------- Forecasts ----------------
    def add_forecast(self, forecast: PortfolioForecast) -> None:
        ws = self._worksheet(SHEET_FORECASTS)
        row = forecast.to_row()
        ws.append_row([str(row.get(f, "")) for f in FORECAST_FIELDS])

    def list_forecasts(self) -> list[PortfolioForecast]:
        headers, rows = self._all_rows(SHEET_FORECASTS)
        out = []
        for r in rows:
            d = self._row_to_dict(headers, r)
            if not d.get("id"):
                continue
            out.append(
                PortfolioForecast(
                    id=d["id"],
                    fecha=date.fromisoformat(d["fecha"]),
                    horizonte_dias=int(d["horizonte_dias"]),
                    vol_pronosticada_anual=float(d["vol_pronosticada_anual"]),
                    metodo=d.get("metodo", "GARCH(1,1)"),
                    composicion_json=d.get("composicion_json", ""),
                    creado_en=datetime.fromisoformat(d["creado_en"]),
                )
            )
        return sorted(out, key=lambda f: f.fecha, reverse=True)

    # ---------------- Archivos procesados (Drive sync) ----------------
    def add_processed_file(self, processed: ProcessedFile) -> None:
        ws = self._worksheet(SHEET_PROCESSED_FILES)
        row = processed.to_row()
        ws.append_row([str(row.get(f, "")) for f in PROCESSED_FILE_FIELDS])

    def list_processed_file_ids(self) -> set[str]:
        headers, rows = self._all_rows(SHEET_PROCESSED_FILES)
        return {self._row_to_dict(headers, r).get("drive_file_id") for r in rows} - {None, ""}

    # ---------------- Auditoría ----------------
    def add_audit_event(self, event: AuditEvent) -> None:
        ws = self._worksheet(SHEET_AUDIT)
        row = event.to_row()
        ws.append_row([str(row.get(f, "")) for f in AUDIT_FIELDS])

    def list_audit_events(self, limit: int = 200) -> list[AuditEvent]:
        headers, rows = self._all_rows(SHEET_AUDIT)
        out = []
        for r in rows:
            d = self._row_to_dict(headers, r)
            if not d.get("id"):
                continue
            out.append(
                AuditEvent(
                    id=d["id"],
                    timestamp=datetime.fromisoformat(d["timestamp"]),
                    usuario=d["usuario"],
                    accion=d["accion"],
                    detalle=d.get("detalle", ""),
                )
            )
        return sorted(out, key=lambda e: e.timestamp, reverse=True)[:limit]
