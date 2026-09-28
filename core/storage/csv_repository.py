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
from datetime import date, datetime
from pathlib import Path

from core.storage.base_repository import BaseRepository
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
    ):
        self.transactions_file = transactions_file
        self.audit_file = audit_file
        self.snapshots_file = snapshots_file
        self.instrumentos_file = instrumentos_file
        self.processed_files_file = processed_files_file
        self.forecasts_file = forecasts_file
        _ensure_file(self.transactions_file, TRANSACTION_FIELDS)
        _ensure_file(self.audit_file, AUDIT_FIELDS)
        _ensure_file(self.snapshots_file, SNAPSHOT_FIELDS)
        _ensure_file(self.instrumentos_file, INSTRUMENTO_FIELDS)
        _ensure_file(self.processed_files_file, PROCESSED_FILE_FIELDS)
        _ensure_file(self.forecasts_file, FORECAST_FIELDS)

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
        if not self.instrumentos_file.exists():
            return []
        out = []
        with self.instrumentos_file.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("ticker"):
                    continue
                out.append(
                    Instrumento(
                        ticker=row["ticker"],
                        tipo_instrumento=TipoInstrumento(row.get("tipo_instrumento") or "ACCION_ARG"),
                        ticker_usd=row.get("ticker_usd") or None,
                        ratio_cedear=float(row["ratio_cedear"]) if row.get("ratio_cedear") else None,
                        nombre=row.get("nombre", ""),
                        actualizado_en=datetime.fromisoformat(row["actualizado_en"]),
                    )
                )
        return out

    # ---------------- Transacciones ----------------
    def add_transaction(self, transaction: Transaction) -> None:
        with self.transactions_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TRANSACTION_FIELDS)
            writer.writerow(transaction.to_row())
        logger.info("Transacción agregada: %s %s %s", transaction.accion, transaction.cantidad, transaction.ticker)

    def list_transactions(self) -> list[Transaction]:
        if not self.transactions_file.exists():
            return []
        out = []
        with self.transactions_file.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("id"):
                    continue
                out.append(
                    Transaction(
                        id=row["id"],
                        id_externo=row.get("id_externo") or None,
                        fecha=date.fromisoformat(row["fecha"]),
                        ticker=row["ticker"],
                        accion=TransactionAction(row["accion"]),
                        cantidad=float(row["cantidad"]),
                        precio=float(row["precio"]),
                        moneda=row.get("moneda", "ARS"),
                        comision=float(row.get("comision") or 0.0),
                        notas=row.get("notas", ""),
                        creado_en=datetime.fromisoformat(row["creado_en"]),
                    )
                )
        return out

    def add_reversal(self, original_id: str, motivo: str, usuario: str) -> Transaction:
        """Nunca se borra ni edita una transacción: se agrega el movimiento inverso."""
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
            AuditEvent(
                usuario=usuario,
                accion="REVERSO_TRANSACCION",
                detalle=f"Reversó {original_id} ({motivo})",
            )
        )
        return reverso

    # ---------------- Snapshots ----------------
    def add_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        with self.snapshots_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDS)
            writer.writerow(snapshot.to_row())

    def list_snapshots(self) -> list[PortfolioSnapshot]:
        if not self.snapshots_file.exists():
            return []
        out = []
        with self.snapshots_file.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("id"):
                    continue
                out.append(
                    PortfolioSnapshot(
                        id=row["id"],
                        fecha=date.fromisoformat(row["fecha"]),
                        valor_total_usd=float(row["valor_total_usd"]),
                        cantidad_posiciones=int(row["cantidad_posiciones"]),
                        volatilidad_anualizada=float(row["volatilidad_anualizada"]) if row.get("volatilidad_anualizada") else None,
                        var_95_pct=float(row["var_95_pct"]) if row.get("var_95_pct") else None,
                        beta_vs_benchmark=float(row["beta_vs_benchmark"]) if row.get("beta_vs_benchmark") else None,
                        correlacion_promedio=float(row["correlacion_promedio"]) if row.get("correlacion_promedio") else None,
                        composicion_json=row.get("composicion_json", ""),
                        creado_en=datetime.fromisoformat(row["creado_en"]),
                    )
                )
        return sorted(out, key=lambda s: s.fecha)

    # ---------------- Forecasts ----------------
    def add_forecast(self, forecast: PortfolioForecast) -> None:
        with self.forecasts_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FORECAST_FIELDS)
            writer.writerow(forecast.to_row())

    def list_forecasts(self) -> list[PortfolioForecast]:
        if not self.forecasts_file.exists():
            return []
        out = []
        with self.forecasts_file.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("id"):
                    continue
                out.append(
                    PortfolioForecast(
                        id=row["id"],
                        fecha=date.fromisoformat(row["fecha"]),
                        horizonte_dias=int(row["horizonte_dias"]),
                        vol_pronosticada_anual=float(row["vol_pronosticada_anual"]),
                        metodo=row.get("metodo", "GARCH(1,1)"),
                        composicion_json=row.get("composicion_json", ""),
                        creado_en=datetime.fromisoformat(row["creado_en"]),
                    )
                )
        return sorted(out, key=lambda f: f.fecha, reverse=True)

    # ---------------- Archivos procesados (Drive sync) ----------------
    def add_processed_file(self, processed: ProcessedFile) -> None:
        with self.processed_files_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PROCESSED_FILE_FIELDS)
            writer.writerow(processed.to_row())

    def list_processed_file_ids(self) -> set[str]:
        if not self.processed_files_file.exists():
            return set()
        with self.processed_files_file.open("r", newline="", encoding="utf-8") as f:
            return {row["drive_file_id"] for row in csv.DictReader(f) if row.get("drive_file_id")}

    # ---------------- Auditoría ----------------
    def add_audit_event(self, event: AuditEvent) -> None:
        with self.audit_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS)
            writer.writerow(event.to_row())

    def list_audit_events(self, limit: int = 200) -> list[AuditEvent]:
        if not self.audit_file.exists():
            return []
        out = []
        with self.audit_file.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("id"):
                    continue
                out.append(
                    AuditEvent(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        usuario=row["usuario"],
                        accion=row["accion"],
                        detalle=row.get("detalle", ""),
                    )
                )
        return sorted(out, key=lambda e: e.timestamp, reverse=True)[:limit]
