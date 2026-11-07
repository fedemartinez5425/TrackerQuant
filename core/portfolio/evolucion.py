"""
Evolución REAL de la cartera: cuánto valía día por día con las cantidades que
tenías ese día (no con los pesos de hoy), cuánta plata pusiste y sacaste, y el
rendimiento sin el efecto de los aportes.

Valuación (en pesos, a cierre de cada día):
- Precio de mercado: el `.BA` de BCBA (CEDEARs y acciones). Si un CEDEAR no
  tiene `.BA`, se usa el teórico ADR / ratio × CCL del día.
- Días sin cotización (feriados, fines de semana): se usa el último precio
  conocido. Esto es para VALUAR; el riesgo sigue sin rellenar entre mercados
  (ver historicos.alinear_dias_comunes).
- Antes de que haya precio de mercado, o si el ticker no tiene ninguno, se
  usa el precio de tu operación.
- USD = pesos / CCL del día.

Flujos (sin cuenta de efectivo): una compra es plata que entra a la cartera
(cantidad × precio + comisión) y una venta es plata que sale (cantidad ×
precio − comisión). Las operaciones en USD se pasan a pesos con el CCL de su
fecha. Aportes netos = suma de los flujos.

Rendimiento (time-weighted), cada día en dos tramos encadenados:
1. Lo que tenías ayer, de cierre a cierre: a = V_viejo_t / V_{t−1} − 1, con
   V_viejo_t = cantidades de ayer × precios de hoy.
2. Las operaciones del día a su precio contra el cierre:
   b = (V_t − V_viejo_t − F_t) / (V_viejo_t + max(F_t, 0)).
r_t = (1 + a)(1 + b) − 1. Una compra grande no mueve el rendimiento (solo
los precios lo mueven); comprar por debajo del cierre suma, la comisión resta.
Convención: las operaciones se toman al cierre del día (el broker opera cerca del
cierre; con una suba intradiaria grande y un aporte grande el día queda sobreestimado).

Los precios de Yahoo vienen ajustados por dividendos y splits: los dividendos
quedan dentro del rendimiento. Un split o cambio de ratio que no esté en tus
transacciones deja el precio de mercado lejos del de tu operación: eso se
avisa (`alertas`).

Reversos: se excluyen (transacciones_efectivas), como en el resto de la app.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from config.settings import settings
from core.viz import formato
from core.storage.models import Currency, Instrumento, TipoInstrumento, Transaction, TransactionAction, transacciones_efectivas

logger = logging.getLogger(__name__)

# Precio de mercado que se mueve más que esto en un día sin operaciones de ese ticker.
UMBRAL_SALTO = 0.30
# Precio de tu operación vs. el de mercado de ese día.
UMBRAL_DESVIO_OPERACION = 0.25
MONEDAS = ("ARS", "USD")


@dataclass
class Alerta:
    fecha: date | None
    ticker: str
    tipo: str  # "salto" | "precio_operacion" | "sin_precio"
    detalle: str


@dataclass
class Evolucion:
    # índice = días hábiles desde la primera operación. Columnas: valor_ars, valor_usd,
    # flujo_ars, flujo_usd, aportes_ars, aportes_usd (acumulados), ccl, retorno_ars, retorno_usd.
    diario: pd.DataFrame
    pesos: pd.DataFrame  # fecha × ticker, peso en el valor del día (0 si no se tenía)
    operaciones: pd.DataFrame  # fecha (hábil), fecha_original, ticker, accion, cantidad, precio, moneda, monto_ars, monto_usd
    alertas: list[Alerta] = field(default_factory=list)

    @property
    def vacia(self) -> bool:
        return self.diario.empty

    def indice(self, moneda: str = "ARS", desde: date | None = None) -> pd.Series:
        """Rendimiento acumulado base 100 desde `desde` (o desde el principio)."""
        r = self._retornos(moneda, desde)
        if r.empty:
            return pd.Series(dtype=float)
        return (1 + r).cumprod() * 100

    def _recorta(self, desde: date | None) -> bool:
        """True si `desde` cae después del primer día (si no, es "todo")."""
        return desde is not None and not self.diario.empty and pd.Timestamp(desde) > self.diario.index[0]

    def _retornos(self, moneda: str, desde: date | None) -> pd.Series:
        r = self.diario[f"retorno_{moneda.lower()}"]
        if self._recorta(desde):
            r = r.loc[r.index >= pd.Timestamp(desde)].copy()
            if not r.empty:
                r.iloc[0] = 0.0  # base 100 al cierre del primer día del período
        return r.dropna()

    def resumen(self, moneda: str = "ARS", desde: date | None = None) -> dict:
        """Valor inicial y final, aportes netos y ganancia del período.
        ganancia = valor final − valor inicial − aportes netos del período."""
        m = moneda.lower()
        d = self.diario
        if d.empty:
            return {}
        if self._recorta(desde):
            ventana = d.loc[d.index >= pd.Timestamp(desde)]
            if ventana.empty:
                return {}
            # El cierre del primer día es la base (igual que el índice): sus flujos ya están adentro.
            valor_inicial = float(ventana[f"valor_{m}"].iloc[0])
            flujos = float(ventana[f"flujo_{m}"].iloc[1:].sum())
        else:
            ventana, valor_inicial = d, 0.0
            flujos = float(ventana[f"flujo_{m}"].sum())
        valor_final = float(ventana[f"valor_{m}"].iloc[-1])
        indice = self.indice(moneda, desde)
        return {
            "desde": ventana.index[0].date(),
            "hasta": ventana.index[-1].date(),
            "valor_inicial": valor_inicial,
            "valor_final": valor_final,
            "aportes_netos": flujos,
            "ganancia": valor_final - valor_inicial - flujos,
            "rendimiento": float(indice.iloc[-1] / 100 - 1) if not indice.empty else None,
            "aportes_totales": float(d[f"aportes_{m}"].iloc[-1]),
        }


# ---------------------------------------------------------------- helpers


def _serie_en(indice: pd.DatetimeIndex, serie: pd.Series | None) -> pd.Series:
    """Último valor conocido en cada día de `indice` (para valuar, no para riesgo)."""
    if serie is None:
        return pd.Series(np.nan, index=indice)
    serie = serie.dropna()
    serie.index = pd.DatetimeIndex(serie.index).tz_localize(None).normalize()
    serie = serie[~serie.index.duplicated(keep="last")].sort_index()
    return serie.reindex(serie.index.union(indice)).ffill().reindex(indice)


def _dia_habil(indice: pd.DatetimeIndex, fecha) -> pd.Timestamp:
    """Primer día del índice >= fecha (una operación de un sábado cae el lunes)."""
    pos = min(indice.searchsorted(pd.Timestamp(fecha)), len(indice) - 1)
    return indice[pos]


def _instrumento(ticker: str, instrumentos: dict[str, Instrumento]) -> Instrumento:
    return instrumentos.get(ticker) or Instrumento(ticker=ticker, tipo_instrumento=TipoInstrumento.ACCION_ARG)


def tickers_necesarios(transacciones: list[Transaction], instrumentos: dict[str, Instrumento]) -> list[str]:
    """Tickers de yfinance para valuar la historia: `.BA` de todo lo operado y
    el ADR de los CEDEARs (respaldo si falta el `.BA`)."""
    tickers = []
    for t in sorted({t.ticker for t in transacciones_efectivas(transacciones)}):
        tickers.append(f"{t}.BA")
        inst = _instrumento(t, instrumentos)
        if inst.tipo_instrumento == TipoInstrumento.CEDEAR and inst.ticker_usd:
            tickers.append(inst.ticker_usd)
    return tickers


def periodo_desde(fecha: date, hoy: date | None = None) -> str:
    """Período de yfinance que cubre desde `fecha` (con un margen de un mes)."""
    from core.data_providers import dias_periodo

    dias = ((hoy or date.today()) - fecha).days + 31
    for periodo in ("1y", "2y", "3y", "5y", "10y"):
        if dias_periodo(periodo) >= dias:
            return periodo
    return "max"


# ---------------------------------------------------------------- cálculo


def calcular_evolucion(
    transacciones: list[Transaction],
    instrumentos: dict[str, Instrumento],
    precios: pd.DataFrame,
    ccl: pd.Series | None,
    hasta: date | None = None,
) -> Evolucion:
    """Función pura: `precios` es una matriz fecha × ticker de yfinance (cierres)
    y `ccl` la serie diaria de CCL. Sin red ni storage."""
    efectivas = sorted(transacciones_efectivas(transacciones), key=lambda t: (t.fecha, t.creado_en))
    if not efectivas:
        return Evolucion(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    hasta = hasta or date.today()
    indice = pd.bdate_range(efectivas[0].fecha, max(hasta, efectivas[0].fecha))
    if len(indice) == 0:  # primera operación en fin de semana y hasta == ese día
        indice = pd.DatetimeIndex([pd.Timestamp(efectivas[0].fecha)])
    ccl_dia = _serie_en(indice, ccl).bfill() if ccl is not None else pd.Series(np.nan, index=indice)
    alertas: list[Alerta] = []

    # --- operaciones, flujos y precios de cada operación (en pesos)
    filas = []
    for t in efectivas:
        dia = _dia_habil(indice, t.fecha)
        fx = ccl_dia.get(dia)
        factor = 1.0
        if t.moneda == Currency.USD:
            if pd.notna(fx):
                factor = float(fx)
            else:
                logger.warning("Sin CCL para %s (%s, USD): se toma el precio sin convertir.", t.id, t.ticker)
        bruto = t.cantidad * t.precio
        neto = bruto + t.comision if t.accion == TransactionAction.COMPRA else -(bruto - t.comision)
        monto_ars = neto * factor
        if t.moneda == Currency.USD:
            monto_usd = neto
        else:
            monto_usd = monto_ars / fx if pd.notna(fx) and fx else np.nan
        filas.append({
            "fecha": dia, "fecha_original": t.fecha, "ticker": t.ticker, "accion": t.accion.value,
            "cantidad": t.cantidad, "precio": t.precio, "moneda": t.moneda.value,
            "precio_ars": t.precio * factor, "monto_ars": monto_ars, "monto_usd": monto_usd,
            "delta": t.cantidad if t.accion == TransactionAction.COMPRA else -t.cantidad,
        })
    ops = pd.DataFrame(filas)
    tickers = list(dict.fromkeys(ops["ticker"]))

    # --- cantidades por día
    deltas = ops.pivot_table(index="fecha", columns="ticker", values="delta", aggfunc="sum")
    cantidades = deltas.reindex(indice).fillna(0).cumsum()[tickers].clip(lower=0)
    cantidades[cantidades.abs() < 1e-9] = 0.0

    # --- precio en pesos por día y ticker
    precios_dia = pd.DataFrame(index=indice, columns=tickers, dtype=float)
    mercado_dia = pd.DataFrame(index=indice, columns=tickers, dtype=float)
    for tk in tickers:
        inst = _instrumento(tk, instrumentos)
        mercado = _serie_en(indice, precios[f"{tk}.BA"]) if f"{tk}.BA" in precios.columns else _serie_en(indice, None)
        if (inst.tipo_instrumento == TipoInstrumento.CEDEAR and inst.ticker_usd and inst.ratio_cedear
                and inst.ticker_usd in precios.columns):
            teorico = _serie_en(indice, precios[inst.ticker_usd]) / inst.ratio_cedear * ccl_dia
            mercado = mercado.combine_first(teorico)
        mercado_dia[tk] = mercado
        # Precio de las operaciones (último del día) para los días sin mercado.
        de_ops = ops[ops["ticker"] == tk].groupby("fecha")["precio_ars"].last()
        precios_dia[tk] = mercado.combine_first(de_ops.reindex(indice)).ffill()
        if mercado.isna().all():
            alertas.append(Alerta(None, tk, "sin_precio",
                                  f"{tk}: sin precio de mercado; se valúa al precio de tu última operación."))

    valores = (cantidades * precios_dia).fillna(0.0)
    valor_ars = valores.sum(axis=1)

    # --- alertas: precio de la operación lejos del mercado (split / cambio de ratio no cargado)
    for _, op in ops.iterrows():
        m = mercado_dia.at[op["fecha"], op["ticker"]]
        if pd.notna(m) and m > 0 and abs(op["precio_ars"] / m - 1) > UMBRAL_DESVIO_OPERACION:
            alertas.append(Alerta(
                op["fecha_original"], op["ticker"], "precio_operacion",
                f"{op['ticker']} el {op['fecha_original']:%d/%m/%Y}: operaste a {formato.moneda(op['precio_ars'])} y el "
                f"mercado cerró a {formato.moneda(m)} ({formato.pct(op['precio_ars'] / m - 1, 0, signo=True)}). "
                "¿Hubo un split o cambio de ratio que no está cargado?",
            ))

    # --- alertas: salto de precio en un día sin operaciones de ese ticker
    variacion = mercado_dia.ffill().pct_change(fill_method=None)
    dias_con_op = set(zip(ops["fecha"], ops["ticker"]))
    for tk in tickers:
        sospechosos = variacion.index[(variacion[tk].abs() > UMBRAL_SALTO) & (cantidades[tk].shift(1) > 0)]
        for dia in sospechosos:
            if (dia, tk) not in dias_con_op:
                alertas.append(Alerta(
                    dia.date(), tk, "salto",
                    f"{tk} el {dia:%d/%m/%Y}: el precio se movió {formato.pct(variacion.at[dia, tk], 0, signo=True)} en un día. "
                    "Si fue un split o cambio de ratio, la cantidad cargada no coincide.",
                ))

    # --- flujos, aportes y rendimiento
    flujo_ars = ops.groupby("fecha")["monto_ars"].sum().reindex(indice).fillna(0.0)
    flujo_usd = ops.groupby("fecha")["monto_usd"].sum(min_count=1).reindex(indice).fillna(0.0)
    if ops["monto_usd"].isna().any():
        flujo_usd[:] = np.nan
    valor_usd = valor_ars / ccl_dia

    diario = pd.DataFrame({
        "valor_ars": valor_ars, "valor_usd": valor_usd,
        "flujo_ars": flujo_ars, "flujo_usd": flujo_usd,
        "aportes_ars": flujo_ars.cumsum(), "aportes_usd": flujo_usd.cumsum(),
        "ccl": ccl_dia,
    })
    viejo_ars = (cantidades.shift(1).fillna(0.0) * precios_dia).fillna(0.0).sum(axis=1)
    diario["retorno_ars"] = rendimiento_diario(diario["valor_ars"], diario["flujo_ars"], viejo_ars)
    diario["retorno_usd"] = rendimiento_diario(diario["valor_usd"], diario["flujo_usd"], viejo_ars / ccl_dia)

    pesos = valores.div(valor_ars.where(valor_ars > 0), axis=0).fillna(0.0)
    ops["valor_dia_ars"] = ops["fecha"].map(valor_ars)
    ops["valor_dia_usd"] = ops["fecha"].map(valor_usd)
    return Evolucion(diario, pesos, ops.drop(columns=["delta"]), alertas)


def rendimiento_diario(valor: pd.Series, flujo: pd.Series, valor_viejo: pd.Series) -> pd.Series:
    """Retorno diario time-weighted en dos tramos (ver docstring del módulo).
    `valor_viejo` = tenencias de ayer a precios de hoy. NaN si falta el CCL."""
    anterior = valor.shift(1).fillna(0.0)
    a = (valor_viejo / anterior.where(anterior > 0) - 1).fillna(0.0)
    base = valor_viejo + flujo.clip(lower=0)
    b = ((valor - valor_viejo - flujo) / base.where(base > 0)).fillna(0.0)
    r = (1 + a) * (1 + b) - 1
    faltan = valor.isna() | flujo.isna() | valor_viejo.isna()
    return r.mask(faltan)


def referencias(evo: Evolucion, precios: pd.DataFrame, moneda: str, desde: date | None = None) -> pd.DataFrame:
    """Contra qué compararte, base 100 en el mismo período: el benchmark (SPY)
    y, en pesos, el dólar CCL (¿le ganaste a dolarizarte?)."""
    d = evo.diario if desde is None else evo.diario.loc[evo.diario.index >= pd.Timestamp(desde)]
    if d.empty:
        return pd.DataFrame()
    bench = settings.DEFAULT_BENCHMARK
    series = {}
    if bench in precios.columns:
        b = _serie_en(d.index, precios[bench])
        series[bench] = b * d["ccl"] if moneda == "ARS" else b
    if moneda == "ARS":
        series["Dólar CCL"] = d["ccl"]
    out = pd.DataFrame(series)
    return out / out.bfill().iloc[0] * 100 if not out.empty else out


# ---------------------------------------------------------------- datos (red/almacén)


def cargar_mercado(transacciones: list[Transaction], instrumentos: dict[str, Instrumento],
                   hoy: date | None = None) -> tuple[pd.DataFrame, pd.Series | None]:
    """Precios (matriz fecha × ticker) y CCL para `calcular_evolucion`, en lote
    y desde el almacén cuando está."""
    from core import data_providers
    from core.data_providers.ccl_provider import get_ccl_historico

    efectivas = transacciones_efectivas(transacciones)
    if not efectivas:
        return pd.DataFrame(), None
    primera = min(t.fecha for t in efectivas)
    periodo = periodo_desde(primera, hoy)
    if data_providers.dias_periodo(periodo) < data_providers.dias_periodo(settings.HISTORY_PERIOD_BASE):
        periodo = settings.HISTORY_PERIOD_BASE  # misma descarga que el resto de la app
    tickers = tickers_necesarios(transacciones, instrumentos) + [settings.DEFAULT_BENCHMARK]
    pares = [t for ars, usd, _ in settings.CCL_PARES for t in (ars, usd)]
    data_providers.precargar(tickers, periodo)
    periodo_ccl = periodo if data_providers.dias_periodo(periodo) > data_providers.dias_periodo("5y") else "5y"
    data_providers.precargar(pares, periodo_ccl)

    frames = []
    for t in tickers:
        h = data_providers.get_history(t, period=periodo)
        if h is not None and not h.empty and t in h.columns:
            frames.append(h[t])
    precios = pd.concat(frames, axis=1, sort=True) if frames else pd.DataFrame()
    return precios, get_ccl_historico(periodo_ccl)
