"""
Impacto de la última operación: cómo cambió el riesgo de la cartera con la
última compra o venta. "Antes" = la cartera sin esa operación, "después" =
la cartera de hoy; las dos valuadas a precios de hoy y medidas sobre los
mismos históricos, así la diferencia es solo por la operación.

Es un backtest con pesos constantes (como el resto de la app): describe el
riesgo histórico de la nueva composición, no predice el futuro.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.risk.summary import calcular_resumen_riesgo
from core.storage.models import Transaction, transacciones_efectivas


@dataclass(frozen=True)
class FilaImpacto:
    metrica: str
    antes: float | None
    despues: float | None
    formato: str            # "pct" | "moneda" | "num"
    sube_es_malo: bool | None  # None: neutro (ni bueno ni malo por sí solo)
    ayuda: str = ""

    @property
    def delta(self) -> float | None:
        if self.antes is None or self.despues is None:
            return None
        return self.despues - self.antes

    @property
    def empeora(self) -> bool:
        if self.sube_es_malo is None or self.delta is None:
            return False
        return self.delta > 0 if self.sube_es_malo else self.delta < 0


def ultima_operacion(transacciones: list[Transaction]) -> Transaction | None:
    """La operación efectiva más reciente (por fecha y, a igual fecha, por alta)."""
    efectivas = transacciones_efectivas(transacciones)
    if not efectivas:
        return None
    return max(efectivas, key=lambda t: (t.fecha, t.creado_en))


def sin_operacion(transacciones: list[Transaction], operacion: Transaction) -> list[Transaction]:
    return [t for t in transacciones if t.id != operacion.id]


def comparar_riesgo(
    historicos: pd.DataFrame,
    pesos_antes: dict[str, float],
    pesos_despues: dict[str, float],
    valor_antes: float,
    valor_despues: float,
    ticker: str,
    benchmark: str,
) -> list[FilaImpacto]:
    """Filas antes/después. `historicos` tiene que cubrir los tickers de las
    dos carteras (alineados en días comunes)."""
    if historicos.empty:
        return []
    antes = calcular_resumen_riesgo(historicos, pesos_antes, valor_antes, benchmark) if pesos_antes else None
    despues = calcular_resumen_riesgo(historicos, pesos_despues, valor_despues, benchmark)

    def _de(riesgo: dict | None, clave: str):
        return riesgo.get(clave) if riesgo else None

    def _perdida(riesgo: dict | None, clave: str):
        """El VaR viene como retorno negativo: se muestra como pérdida positiva."""
        v = _de(riesgo, clave)
        return abs(v) if v is not None else None

    def _aporte(riesgo: dict | None):
        if not riesgo:
            return None
        contrib = riesgo["contribucion_riesgo"]
        return float(contrib[ticker]) if ticker in contrib.index else 0.0

    return [
        FilaImpacto(
            f"Peso de {ticker}", pesos_antes.get(ticker, 0.0) if pesos_antes else None,
            pesos_despues.get(ticker, 0.0), "pct", None, "Qué parte de la cartera es este activo.",
        ),
        FilaImpacto(
            f"Aporte de {ticker} al riesgo", _aporte(antes), _aporte(despues), "pct", True,
            "Qué parte de la volatilidad total viene de este activo. Si es mucho mayor que su peso, "
            "el activo pesa más en el riesgo que en la plata.",
        ),
        FilaImpacto(
            "Volatilidad anual", _de(antes, "volatilidad_anualizada"), _de(despues, "volatilidad_anualizada"),
            "pct", True, "Cuánto se mueve la cartera en un año típico (desvío anualizado).",
        ),
        FilaImpacto(
            "Pérdida en un mal día (VaR 95%)", _perdida(antes, "var_95_usd"), _perdida(despues, "var_95_usd"),
            "moneda", True,
            "En 1 de cada 20 días la pérdida diaria fue mayor a este monto. Sube también por tener más plata invertida.",
        ),
        FilaImpacto(
            "VaR 95% (% de la cartera)", _perdida(antes, "var_95_pct"), _perdida(despues, "var_95_pct"), "pct", True,
            "El mismo VaR como porcentaje: compara el riesgo sin el efecto del monto invertido.",
        ),
        FilaImpacto(
            "Riesgo en las 2 mayores posiciones", _de(antes, "concentracion_top2"), _de(despues, "concentracion_top2"),
            "pct", True, "Qué parte del riesgo total viene de solo 2 activos.",
        ),
        FilaImpacto(
            "Correlación promedio", _de(antes, "correlacion_ponderada"), _de(despues, "correlacion_ponderada"),
            "num", True, "Cuánto se mueven juntas las posiciones (más alto = menos diversificación).",
        ),
        FilaImpacto(
            f"Beta vs. {benchmark}", _de(antes, "beta_cartera"), _de(despues, "beta_cartera"), "num", None,
            "Cuánto amplifica la cartera los movimientos del mercado (1 = igual que el mercado).",
        ),
    ]


def lectura_impacto(filas: list[FilaImpacto], ticker: str, peso_alto: float, peso_medio: float) -> list[tuple[str, str]]:
    """Conclusiones en texto llano, de más a menos grave: [(severidad, texto)]
    con severidad "alto" | "medio" | "bajo". Los textos usan formato argentino."""
    from core.viz.formato import pct

    por_metrica = {f.metrica: f for f in filas}
    peso = por_metrica.get(f"Peso de {ticker}")
    aporte = por_metrica.get(f"Aporte de {ticker} al riesgo")
    vol = por_metrica.get("Volatilidad anual")
    lecturas: list[tuple[str, str]] = []

    if peso and peso.despues is not None:
        if peso.despues > peso_alto:
            lecturas.append(("alto", f"{ticker} pasó a pesar {pct(peso.despues, 1)} de la cartera: más de {pct(peso_alto, 0)} es concentración alta."))
        elif peso.despues > peso_medio:
            lecturas.append(("medio", f"{ticker} pesa {pct(peso.despues, 1)} de la cartera (más de {pct(peso_medio, 0)})."))
    if aporte and peso and aporte.despues and peso.despues and aporte.despues > 1.5 * peso.despues:
        lecturas.append((
            "medio",
            f"{ticker} aporta {pct(aporte.despues, 1)} del riesgo con {pct(peso.despues, 1)} del peso: "
            "mueve la cartera más de lo que indica su tamaño.",
        ))
    if vol and vol.delta is not None:
        cambio = f"de {pct(vol.antes, 1)} a {pct(vol.despues, 1)}"
        if vol.delta > 0.01:
            lecturas.append(("medio", f"La volatilidad anual de la cartera subió {cambio}."))
        elif vol.delta < -0.01:
            lecturas.append(("bajo", f"La volatilidad anual de la cartera bajó {cambio}: la operación diversificó."))
        else:
            lecturas.append(("bajo", f"La volatilidad anual casi no cambió ({cambio})."))
    orden = {"alto": 0, "medio": 1, "bajo": 2}
    return sorted(lecturas, key=lambda t: orden[t[0]])
