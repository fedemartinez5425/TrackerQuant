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

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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
