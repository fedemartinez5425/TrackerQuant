"""
Foto diaria de la cartera (pestaña `portfolio_snapshots`). La usan el botón
del Dashboard y el ETL diario (snapshot automático), con la misma lógica.
"""
from __future__ import annotations

import json
from datetime import date

from core.storage.models import PortfolioSnapshot


def armar_snapshot(resumen: dict, riesgo: dict, pesos: dict[str, float], ccl: float, fecha: date | None = None) -> PortfolioSnapshot:
    """`valor_total_usd` en USD: valor en pesos / CCL de hoy."""
    return PortfolioSnapshot(
        fecha=fecha or date.today(),
        valor_total_usd=resumen["valor_actual_total"] / ccl,
        cantidad_posiciones=resumen["cantidad_posiciones"],
        volatilidad_anualizada=riesgo["volatilidad_anualizada"],
        var_95_pct=riesgo["var_95_pct"],
        beta_vs_benchmark=riesgo["beta_cartera"],
        correlacion_promedio=riesgo["correlacion_ponderada"],
        composicion_json=json.dumps(pesos),
    )


def hay_snapshot_en_fecha(snapshots: list[PortfolioSnapshot], fecha: date) -> bool:
    return any(s.fecha == fecha for s in snapshots)
