"""
ETL diario de precios (lo corre GitHub Actions después del cierre de EE.UU.):

1. Extracción: arma el universo (instrumentos, tickers con transacciones,
   watchlist, benchmark y pares del CCL) y lo baja de Yahoo en lote.
   Se baja la ventana COMPLETA todos los días (no incremental): Yahoo ajusta
   el pasado por dividendos y splits, y pegar días nuevos sobre una historia
   vieja dejaría saltos falsos.
2. Controles de calidad (core/data_providers/calidad.py).
3. Carga: reescribe la pestaña `precios`. Si se bajó mucho menos que lo que
   ya había guardado, NO pisa el almacén (mejor datos de ayer que un agujero).
4. Snapshot automático de la cartera (si todavía no hay uno de hoy).
5. Registro en `audit_log`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd

from config.settings import settings
from core import data_providers
from core.data_providers.calidad import Problema, controlar_precios
from core.portfolio.historicos import InstrumentoRiesgo, tickers_de_mercado
from core.storage.base_repository import BaseRepository
from core.storage.models import AuditEvent, Instrumento, PrecioCierre, TipoInstrumento, transacciones_efectivas

logger = logging.getLogger(__name__)

# Los pares del CCL se guardan con más historia: el CCL histórico (G/P en USD
# de compras viejas) se pide a 5 años en cada visita.
PERIODO_CCL = "5y"
# No se pisa el almacén si esta corrida trae menos de esta fracción de los tickers ya guardados.
MINIMO_TICKERS_VS_ANTERIOR = 0.5
USUARIO_ETL = "etl"


@dataclass
class ResultadoETL:
    tickers_esperados: list[str]
    tickers_bajados: list[str]
    filas: int = 0
    guardado: bool = False
    snapshot: str = ""
    problemas: list[Problema] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.guardado and self.error is None

    def resumen(self) -> str:
        estado = "OK" if self.ok else f"FALLÓ ({self.error})"
        return (
            f"ETL precios {estado}: {len(self.tickers_bajados)}/{len(self.tickers_esperados)} tickers, "
            f"{self.filas} filas. Snapshot: {self.snapshot or '—'}. Problemas de calidad: {len(self.problemas)}."
        )


def universo(repo: BaseRepository) -> list[str]:
    """Tickers de yfinance que la app va a pedir."""
    instrumentos = {i.ticker: i for i in repo.list_instrumentos()}
    for t in {t.ticker for t in transacciones_efectivas(repo.list_transactions())}:
        instrumentos.setdefault(t, Instrumento(ticker=t, tipo_instrumento=TipoInstrumento.ACCION_ARG))
    riesgo = [InstrumentoRiesgo(i.ticker, i.tipo_instrumento, i.ticker_usd) for i in instrumentos.values()]
    riesgo += [InstrumentoRiesgo(w.ticker, w.tipo_instrumento, w.ticker_usd) for w in repo.list_watchlist()]
    tickers = set(tickers_de_mercado(riesgo)) | {settings.DEFAULT_BENCHMARK}
    tickers |= {t for ars, usd, _ in settings.CCL_PARES for t in (ars, usd)}
    return sorted(tickers)


def _pares_ccl() -> list[str]:
    return [t for ars, usd, _ in settings.CCL_PARES for t in (ars, usd)]


def extraer(tickers: list[str]) -> pd.DataFrame:
    """Matriz fecha × ticker con la ventana completa, en lote."""
    data_providers.limpiar_cache()  # siempre datos nuevos (y sin almacén: se baja todo)
    data_providers.precargar([t for t in tickers if t not in _pares_ccl()], settings.HISTORY_PERIOD_BASE)
    data_providers.precargar(_pares_ccl(), PERIODO_CCL)
    frames = []
    for t in tickers:
        periodo = PERIODO_CCL if t in _pares_ccl() else settings.HISTORY_PERIOD_BASE
        h = data_providers.get_history(t, period=periodo)  # del cache; si faltó en el lote, reintenta solo
        if h is not None and not h.empty and t in h.columns:
            frames.append(h[t])
    return pd.concat(frames, axis=1, sort=True) if frames else pd.DataFrame()


def a_filas(matriz: pd.DataFrame, actualizado_en: datetime) -> list[PrecioCierre]:
    largo = matriz.stack().dropna()
    return [
        PrecioCierre(fecha=fecha.date(), ticker=ticker, close=float(valor), actualizado_en=actualizado_en)
        for (fecha, ticker), valor in largo.items()
    ]


def snapshot_automatico(repo: BaseRepository, hoy: date) -> str:
    """Guarda la foto de hoy con la misma lógica que el botón del Dashboard."""
    from core.data_providers.ccl_provider import get_ccl_automatico
    from core.portfolio.historicos import desde_posiciones, historicos_usd_equivalente, matriz_riesgo
    from core.portfolio.portfolio_engine import construir_cartera, resumen_cartera
    from core.portfolio.snapshot import armar_snapshot, hay_snapshot_en_fecha
    from core.risk.summary import calcular_resumen_riesgo

    if hay_snapshot_en_fecha(repo.list_snapshots(), hoy):
        return "ya había uno de hoy"
    instrumentos = {i.ticker: i for i in repo.list_instrumentos()}
    posiciones = construir_cartera(repo.list_transactions(), instrumentos)
    if not posiciones:
        return "sin posiciones"
    ccl = get_ccl_automatico()
    if not ccl:
        return "sin CCL (no se guardó)"
    resumen = resumen_cartera(posiciones)
    pesos = {p.ticker: p.peso for p in posiciones if p.peso}
    historicos = matriz_riesgo(
        historicos_usd_equivalente(desde_posiciones(posiciones), settings.HISTORY_PERIOD),
        data_providers.get_history_multi([settings.DEFAULT_BENCHMARK], settings.HISTORY_PERIOD),
    )
    if historicos.empty:
        return "sin históricos (no se guardó)"
    riesgo = calcular_resumen_riesgo(
        historicos, pesos, resumen["valor_actual_total"], settings.DEFAULT_BENCHMARK, settings.STRESS_SCENARIOS
    )
    snapshot = armar_snapshot(resumen, riesgo, pesos, ccl["valor"], fecha=hoy)
    repo.add_snapshot(snapshot)
    return f"guardado (US$ {snapshot.valor_total_usd:,.2f})"


def correr(repo: BaseRepository, con_snapshot: bool = True, escribir: bool = True, hoy: date | None = None) -> ResultadoETL:
    hoy = hoy or date.today()
    ahora = datetime.now(timezone.utc)
    tickers = universo(repo)
    matriz = extraer(tickers)
    resultado = ResultadoETL(tickers_esperados=tickers, tickers_bajados=sorted(matriz.columns))
    resultado.problemas = controlar_precios(matriz, tickers, settings.CCL_PARES)

    if matriz.empty:
        resultado.error = "Yahoo no devolvió ningún precio"
    else:
        anteriores = {p.ticker for p in repo.list_precios()}
        if anteriores and len(matriz.columns) < MINIMO_TICKERS_VS_ANTERIOR * len(anteriores):
            resultado.error = (
                f"solo se bajaron {len(matriz.columns)} tickers contra {len(anteriores)} guardados: "
                "no se pisa el almacén"
            )
    if resultado.error is None:
        filas = a_filas(matriz, ahora)
        resultado.filas = len(filas)
        if escribir:
            repo.reemplazar_precios(filas)
        resultado.guardado = True

    if con_snapshot and escribir:
        try:
            resultado.snapshot = snapshot_automatico(repo, hoy)
        except Exception as exc:  # noqa: BLE001 - el snapshot no invalida los precios ya guardados
            logger.exception("Falló el snapshot automático")
            resultado.snapshot = f"falló: {type(exc).__name__}: {exc}"

    if escribir:
        detalle = resultado.resumen()
        if resultado.problemas:
            detalle += " | " + " | ".join(str(p) for p in resultado.problemas[:15])
        repo.add_audit_event(AuditEvent(usuario=USUARIO_ETL, accion="ETL_PRECIOS", detalle=detalle[:4000]))
    logger.info(resultado.resumen())
    return resultado


def ultima_corrida(repo: BaseRepository) -> AuditEvent | None:
    """Para Estado del sistema: el último registro del ETL en audit_log."""
    return next((e for e in repo.list_audit_events(limit=500) if e.accion == "ETL_PRECIOS"), None)
