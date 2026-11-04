"""
Controles de calidad sobre la matriz de precios (fecha × ticker) que arma el
ETL, antes de guardarla. Un dato malo de Yahoo (split no ajustado, precio
congelado, ratio del CCL desactualizado) pasaba directo al riesgo sin que
nadie se enterara; ahora queda registrado y se ve en Estado del sistema.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

import pandas as pd

SALTO_DIARIO_MAXIMO = 0.40     # |retorno diario| mayor: posible split o dato roto
RUEDAS_DESACTUALIZADO = 4      # último precio más viejo que esto vs. el resto: congelado
HUECO_MAXIMO_DIAS = 10         # días corridos sin precio dentro de la serie
DISPERSION_CCL_MAXIMA = 0.05   # un par del CCL que se aleja más de esto de la mediana


@dataclass(frozen=True)
class Problema:
    severidad: str  # "alto" | "medio"
    ticker: str
    tipo: str       # faltante | desactualizado | salto | hueco | ccl
    detalle: str

    def __str__(self) -> str:
        return f"[{self.severidad}] {self.ticker} · {self.tipo}: {self.detalle}"


def controlar_precios(matriz: pd.DataFrame, esperados: list[str], pares_ccl: tuple = ()) -> list[Problema]:
    problemas: list[Problema] = []
    if matriz.empty:
        return [Problema("alto", "*", "faltante", "No se bajó ningún precio.")]
    referencia = matriz.index.max()

    for ticker in sorted(set(esperados)):
        if ticker not in matriz.columns or matriz[ticker].dropna().empty:
            problemas.append(Problema("alto", ticker, "faltante", "Yahoo no devolvió historia (¿ticker mal escrito o deslistado?)."))
            continue
        s = matriz[ticker].dropna()

        ruedas_atras = len(pd.bdate_range(s.index.max(), referencia)) - 1
        if ruedas_atras > RUEDAS_DESACTUALIZADO:
            problemas.append(Problema(
                "medio", ticker, "desactualizado",
                f"Último precio del {s.index.max():%d/%m/%Y} ({ruedas_atras} ruedas atrás del resto).",
            ))

        retornos = s.pct_change().dropna()
        saltos = retornos[retornos.abs() > SALTO_DIARIO_MAXIMO]
        if not saltos.empty:
            fecha, valor = saltos.abs().idxmax(), saltos.loc[saltos.abs().idxmax()]
            problemas.append(Problema(
                "medio", ticker, "salto",
                f"Movimiento de {valor:+.0%} el {fecha:%d/%m/%Y} ({len(saltos)} día(s) con más de "
                f"{SALTO_DIARIO_MAXIMO:.0%}): ¿split sin ajustar?",
            ))

        huecos = s.index.to_series().diff().dt.days
        if not huecos.empty and huecos.max() > HUECO_MAXIMO_DIAS:
            fin = huecos.idxmax()
            problemas.append(Problema(
                "medio", ticker, "hueco", f"{int(huecos.max())} días sin precio hasta el {fin:%d/%m/%Y}.",
            ))

    problemas += _controlar_ccl(matriz, pares_ccl)
    return problemas


def _controlar_ccl(matriz: pd.DataFrame, pares_ccl: tuple) -> list[Problema]:
    """Cada par del CCL contra la mediana de todos, en la última fecha en que
    cotizaron ambas puntas. Detecta ratios cargados mal o desactualizados."""
    valores: dict[str, float] = {}
    for ticker_ars, ticker_usd, ratio in pares_ccl:
        if ticker_ars not in matriz.columns or ticker_usd not in matriz.columns:
            continue
        ambos = matriz[[ticker_ars, ticker_usd]].dropna()
        if ambos.empty:
            continue
        ultima = ambos.iloc[-1]
        valores[f"{ticker_ars}/{ticker_usd} ({ratio:g}:1)"] = ultima[ticker_ars] * ratio / ultima[ticker_usd]
    if len(valores) < 2:
        return []
    mediana = statistics.median(valores.values())
    return [
        Problema(
            "alto", par, "ccl",
            f"Da un CCL de {v:,.2f} contra una mediana de {mediana:,.2f} ({v / mediana - 1:+.0%}): "
            "revisá el ratio en settings.CCL_PARES.",
        )
        for par, v in valores.items()
        if abs(v / mediana - 1) > DISPERSION_CCL_MAXIMA
    ]
