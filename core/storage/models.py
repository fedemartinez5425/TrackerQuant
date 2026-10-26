"""
Entidades del sistema, validadas con Pydantic.
Ninguna fila entra a storage (CSV o Google Sheets) sin pasar por acá.

Diseño relacional:
- `instrumentos` es la tabla dimensión (maestro de cada ticker: tipo,
  ADR, ratio). Se define UNA vez por ticker.
- `transactions` es la tabla de hechos (append-only) y solo referencia
  el ticker -- no repite tipo/ratio/ticker_usd en cada fila. Si un ratio
  cambia (ampliación de capital, split), se corrige en un solo lugar.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def _opt_float(valor) -> Optional[float]:
    """'' / None -> None; cualquier otro valor -> float. Para leer filas de CSV/Sheets."""
    if valor is None or str(valor).strip() == "":
        return None
    return float(valor)


class Currency(str, Enum):
    ARS = "ARS"
    USD = "USD"


class TransactionAction(str, Enum):
    COMPRA = "COMPRA"
    VENTA = "VENTA"


class TipoInstrumento(str, Enum):
    ACCION_ARG = "ACCION_ARG"  # acción argentina comprada directamente en pesos (ej: PAMP, GGAL)
    CEDEAR = "CEDEAR"          # CEDEAR de instrumento extranjero (ej: AMZN, AAPL)


class Instrumento(BaseModel):
    """Tabla dimensión: metadata de cada ticker, definida una sola vez.
    Es la fuente de verdad para tipo/ratio/ADR -- las transacciones solo
    referencian el ticker."""

    ticker: str  # PK -- ticker BCBA (ej: AMZN, GGAL, YPFD, PAMP)
    tipo_instrumento: TipoInstrumento = TipoInstrumento.ACCION_ARG
    ticker_usd: Optional[str] = None  # ticker del ADR en EEUU (solo si es CEDEAR)
    ratio_cedear: Optional[float] = None  # X CEDEARs = 1 ADR (solo si es CEDEAR)
    nombre: str = ""
    actualizado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("ticker", "ticker_usd")
    @classmethod
    def ticker_uppercase(cls, v):
        return v.upper().strip() if v else v

    @field_validator("ratio_cedear")
    @classmethod
    def ratio_positivo(cls, v):
        if v is not None and v <= 0:
            raise ValueError("El ratio CEDEAR debe ser mayor a 0")
        return v

    @model_validator(mode="after")
    def validar_consistencia(self):
        if self.tipo_instrumento == TipoInstrumento.CEDEAR:
            if not self.ratio_cedear:
                raise ValueError("Un CEDEAR necesita un ratio_cedear (X CEDEARs = 1 ADR).")
            if not self.ticker_usd:
                raise ValueError("Un CEDEAR necesita el ticker_usd (ADR en EEUU).")
        else:  # ACCION_ARG
            if self.ratio_cedear:
                raise ValueError("Una acción argentina directa no debería tener ratio_cedear.")
        return self

    def to_row(self) -> dict:
        d = self.model_dump()
        d["tipo_instrumento"] = self.tipo_instrumento.value
        d["actualizado_en"] = self.actualizado_en.isoformat()
        return d

    @classmethod
    def from_row(cls, d: dict) -> "Instrumento":
        return cls(
            ticker=d["ticker"],
            tipo_instrumento=TipoInstrumento(d.get("tipo_instrumento") or "ACCION_ARG"),
            ticker_usd=d.get("ticker_usd") or None,
            ratio_cedear=_opt_float(d.get("ratio_cedear")),
            nombre=d.get("nombre") or "",
            actualizado_en=datetime.fromisoformat(d["actualizado_en"]),
        )


class WatchlistItem(BaseModel):
    """Candidato que todavía no está en cartera (pestaña `watchlist`).
    Es independiente de `instrumentos`: si el ticker se compra, se da de
    alta ahí como siempre. El ratio es opcional (si falta, se busca en Comafi)."""

    ticker: str  # PK -- ticker BCBA
    tipo_instrumento: TipoInstrumento = TipoInstrumento.CEDEAR
    ticker_usd: Optional[str] = None
    ratio_cedear: Optional[float] = None
    notas: str = ""
    agregado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("ticker", "ticker_usd")
    @classmethod
    def ticker_uppercase(cls, v):
        return v.upper().strip() if v else v

    @field_validator("ratio_cedear")
    @classmethod
    def ratio_positivo(cls, v):
        if v is not None and v <= 0:
            raise ValueError("El ratio CEDEAR debe ser mayor a 0")
        return v

    @model_validator(mode="after")
    def validar_consistencia(self):
        if self.tipo_instrumento == TipoInstrumento.CEDEAR:
            if not self.ticker_usd:
                raise ValueError("Un CEDEAR necesita el ticker_usd (ADR en EEUU).")
        elif self.ratio_cedear:
            raise ValueError("Una acción argentina directa no debería tener ratio_cedear.")
        return self

    def to_row(self) -> dict:
        d = self.model_dump()
        d["tipo_instrumento"] = self.tipo_instrumento.value
        d["agregado_en"] = self.agregado_en.isoformat()
        return d

    @classmethod
    def from_row(cls, d: dict) -> "WatchlistItem":
        agregado = d.get("agregado_en")
        return cls(
            ticker=d["ticker"],
            tipo_instrumento=TipoInstrumento(d.get("tipo_instrumento") or "CEDEAR"),
            ticker_usd=d.get("ticker_usd") or None,
            ratio_cedear=_opt_float(d.get("ratio_cedear")),
            notas=d.get("notas") or "",
            agregado_en=datetime.fromisoformat(agregado) if agregado else datetime.now(timezone.utc),
        )


class Transaction(BaseModel):
    """Un movimiento de cartera (tabla de hechos, append-only): nunca se
    edita, se reversa. Solo referencia el ticker -- su tipo/ratio/ADR
    viven en la tabla `instrumentos`."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    id_externo: Optional[str] = None  # nroTicket del broker, para evitar reimportar el mismo movimiento
    fecha: date
    ticker: str  # FK -> Instrumento.ticker
    accion: TransactionAction
    cantidad: float
    precio: float
    moneda: Currency = Currency.ARS
    comision: float = 0.0
    notas: str = ""
    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, v):
        return v.upper().strip() if v else v

    @field_validator("cantidad")
    @classmethod
    def cantidad_positiva(cls, v):
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor a 0")
        return v

    @field_validator("precio")
    @classmethod
    def precio_positivo(cls, v):
        if v <= 0:
            raise ValueError("El precio debe ser mayor a 0")
        return v

    @field_validator("fecha")
    @classmethod
    def fecha_no_futura(cls, v):
        if v > date.today():
            raise ValueError("La fecha no puede ser futura")
        return v

    def to_row(self) -> dict:
        d = self.model_dump()
        d["fecha"] = self.fecha.isoformat()
        d["creado_en"] = self.creado_en.isoformat()
        d["accion"] = self.accion.value
        d["moneda"] = self.moneda.value
        return d

    @classmethod
    def from_row(cls, d: dict) -> "Transaction":
        return cls.model_construct(  # sin re-validar: ya se validó al guardar
            id=d["id"],
            id_externo=d.get("id_externo") or None,
            fecha=date.fromisoformat(d["fecha"]),
            ticker=d["ticker"].upper().strip(),
            accion=TransactionAction(d["accion"]),
            cantidad=float(d["cantidad"]),
            precio=float(d["precio"]),
            moneda=Currency(d.get("moneda") or "ARS"),
            comision=float(d.get("comision") or 0.0),
            notas=d.get("notas") or "",
            creado_en=datetime.fromisoformat(d["creado_en"]),
        )

    @property
    def revierte_a(self) -> Optional[str]:
        """Si esta transacción es un reverso, el id de la transacción que anula."""
        match = _PATRON_REVERSO.match(self.notas or "")
        return match.group(1) if match else None


REVERSO_PREFIJO = "REVERSO de "
_PATRON_REVERSO = re.compile(r"^REVERSO de (\S+)")


def ids_reversados(transacciones: list["Transaction"]) -> set[str]:
    """Ids de transacciones anuladas por un reverso."""
    return {t.revierte_a for t in transacciones if t.revierte_a}


def transacciones_efectivas(transacciones: list["Transaction"]) -> list["Transaction"]:
    """Log de transacciones SIN las anuladas y SIN sus reversos.

    Un reverso anula la transacción original por completo: ambas quedan en
    el historial (append-only, auditable) pero ninguna afecta cantidades ni
    costo promedio. Antes el reverso se cargaba como el movimiento inverso
    con fecha de HOY, lo que distorsionaba el costo promedio y la
    reconstrucción de la cartera en fechas pasadas."""
    anuladas = ids_reversados(transacciones)
    return [t for t in transacciones if t.id not in anuladas and not t.revierte_a]


class PortfolioSnapshot(BaseModel):
    """Foto del estado de la cartera en un momento dado (valor total + métricas
    de riesgo). Se guarda manualmente desde el Dashboard ('Guardar snapshot de
    hoy') para construir con el tiempo una serie histórica real, complementaria
    a la reconstrucción retroactiva desde el log de transacciones."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    fecha: date = Field(default_factory=date.today)
    valor_total_usd: float
    cantidad_posiciones: int
    volatilidad_anualizada: Optional[float] = None
    var_95_pct: Optional[float] = None
    beta_vs_benchmark: Optional[float] = None
    correlacion_promedio: Optional[float] = None
    composicion_json: str = ""  # snapshot de {ticker: peso} serializado, para detalle
    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_row(self) -> dict:
        d = self.model_dump()
        d["fecha"] = self.fecha.isoformat()
        d["creado_en"] = self.creado_en.isoformat()
        return d

    @classmethod
    def from_row(cls, d: dict) -> "PortfolioSnapshot":
        return cls(
            id=d["id"],
            fecha=date.fromisoformat(d["fecha"]),
            valor_total_usd=float(d["valor_total_usd"]),
            cantidad_posiciones=int(d["cantidad_posiciones"]),
            volatilidad_anualizada=_opt_float(d.get("volatilidad_anualizada")),
            var_95_pct=_opt_float(d.get("var_95_pct")),
            beta_vs_benchmark=_opt_float(d.get("beta_vs_benchmark")),
            correlacion_promedio=_opt_float(d.get("correlacion_promedio")),
            composicion_json=d.get("composicion_json") or "",
            creado_en=datetime.fromisoformat(d["creado_en"]),
        )


class PortfolioForecast(BaseModel):
    """Log append-only de cada forecast de volatilidad emitido. La
    volatilidad REALIZADA nunca se guarda acá -- se recalcula on-the-fly
    en core/forecasting/backtest.py a partir de composicion_json (los
    pesos vigentes al momento del forecast) + el histórico de precios."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    fecha: date = Field(default_factory=date.today)
    horizonte_dias: int
    vol_pronosticada_anual: float
    metodo: str = "GARCH(1,1)"
    composicion_json: str = ""  # {ticker: peso} vigente al momento del forecast
    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_row(self) -> dict:
        d = self.model_dump()
        d["fecha"] = self.fecha.isoformat()
        d["creado_en"] = self.creado_en.isoformat()
        return d

    @classmethod
    def from_row(cls, d: dict) -> "PortfolioForecast":
        return cls(
            id=d["id"],
            fecha=date.fromisoformat(d["fecha"]),
            horizonte_dias=int(d["horizonte_dias"]),
            vol_pronosticada_anual=float(d["vol_pronosticada_anual"]),
            metodo=d.get("metodo") or "GARCH(1,1)",
            composicion_json=d.get("composicion_json") or "",
            creado_en=datetime.fromisoformat(d["creado_en"]),
        )


class AuditEvent(BaseModel):
    """Registro de auditoría: qué se hizo, cuándo, quién."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    usuario: str
    accion: str
    detalle: str = ""

    def to_row(self) -> dict:
        d = self.model_dump()
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_row(cls, d: dict) -> "AuditEvent":
        return cls(
            id=d["id"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            usuario=d["usuario"],
            accion=d["accion"],
            detalle=d.get("detalle") or "",
        )


class ProcessedFile(BaseModel):
    """Registro de qué archivos de Google Drive ya se importaron, para que
    la sincronización automática nunca reprocese el mismo archivo dos veces."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    drive_file_id: str
    nombre_archivo: str
    tipo_detectado: str = ""  # "movimientos" | "portfolio_report" | "desconocido"
    filas_importadas: int = 0
    procesado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_row(self) -> dict:
        d = self.model_dump()
        d["procesado_en"] = self.procesado_en.isoformat()
        return d
