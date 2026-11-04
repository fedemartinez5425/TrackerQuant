from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from core.decision.ultima_operacion import FilaImpacto, comparar_riesgo, sin_operacion, ultima_operacion
from core.storage.models import REVERSO_PREFIJO, Transaction, TransactionAction


def _t(id_, fecha, ticker="AAPL", notas="", creado=None):
    return Transaction(
        id=id_, fecha=fecha, ticker=ticker, accion=TransactionAction.COMPRA, cantidad=1, precio=10, notas=notas,
        creado_en=creado or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_ultima_operacion_por_fecha_y_alta_e_ignora_reversos():
    a = _t("a", date(2026, 11, 1))
    b = _t("b", date(2026, 11, 3), creado=datetime(2026, 11, 3, 10, tzinfo=timezone.utc))
    c = _t("c", date(2026, 11, 3), creado=datetime(2026, 11, 3, 12, tzinfo=timezone.utc))
    assert ultima_operacion([a, b, c]).id == "c"
    # c revertida: la última efectiva pasa a ser b
    reverso = _t("r", date(2026, 11, 4), notas=f"{REVERSO_PREFIJO}c")
    assert ultima_operacion([a, b, c, reverso]).id == "b"
    assert ultima_operacion([]) is None
    assert [t.id for t in sin_operacion([a, b, c], c)] == ["a", "b"]


def _historicos():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2024-01-01", periods=500)
    mercado = rng.normal(0, 0.01, len(idx))
    datos = {
        "SPY": mercado,
        "KO": 0.4 * mercado + rng.normal(0, 0.006, len(idx)),      # defensiva
        "NVDA": 2.0 * mercado + rng.normal(0, 0.03, len(idx)),     # volátil
    }
    return pd.DataFrame({k: 100 * np.exp(np.cumsum(v)) for k, v in datos.items()}, index=idx)


def test_comprar_un_activo_volatil_sube_volatilidad_y_su_aporte():
    filas = comparar_riesgo(
        _historicos(), pesos_antes={"KO": 1.0}, pesos_despues={"KO": 0.7, "NVDA": 0.3},
        valor_antes=1000, valor_despues=1430, ticker="NVDA", benchmark="SPY",
    )
    por_metrica = {f.metrica: f for f in filas}
    vol = por_metrica["Volatilidad anual"]
    assert vol.despues > vol.antes and vol.empeora
    aporte = por_metrica["Aporte de NVDA al riesgo"]
    assert aporte.antes == 0.0 and aporte.despues > 0.3  # aporta más riesgo que su peso
    assert por_metrica["Peso de NVDA"].antes == 0.0 and por_metrica["Peso de NVDA"].despues == 0.3
    assert por_metrica["Pérdida en un mal día (VaR 95%)"].despues > por_metrica["Pérdida en un mal día (VaR 95%)"].antes


def test_primera_operacion_no_tiene_antes():
    filas = comparar_riesgo(_historicos(), {}, {"KO": 1.0}, 0, 1000, "KO", "SPY")
    assert all(f.antes is None for f in filas)
    assert all(f.delta is None and not f.empeora for f in filas)


def test_fila_impacto_empeora_segun_direccion():
    assert FilaImpacto("x", 0.1, 0.2, "pct", True).empeora
    assert not FilaImpacto("x", 0.2, 0.1, "pct", True).empeora
    assert FilaImpacto("x", 0.2, 0.1, "pct", False).empeora
    assert not FilaImpacto("x", 0.1, 0.9, "pct", None).empeora


def test_lectura_impacto_alerta_concentracion_y_volatilidad():
    from core.decision.ultima_operacion import lectura_impacto

    filas = [
        FilaImpacto("Peso de NVDA", 0.10, 0.30, "pct", None),
        FilaImpacto("Aporte de NVDA al riesgo", 0.15, 0.60, "pct", True),
        FilaImpacto("Volatilidad anual", 0.20, 0.28, "pct", True),
    ]
    lecturas = lectura_impacto(filas, "NVDA", peso_alto=0.25, peso_medio=0.15)
    assert lecturas[0][0] == "alto" and "30,0 %" in lecturas[0][1]
    textos = " ".join(t for _, t in lecturas)
    assert "aporta 60,0 % del riesgo" in textos
    assert "subió de 20,0 % a 28,0 %" in textos


def test_lectura_impacto_diversifica():
    from core.decision.ultima_operacion import lectura_impacto

    filas = [FilaImpacto("Peso de KO", 0.0, 0.10, "pct", None), FilaImpacto("Volatilidad anual", 0.30, 0.25, "pct", True)]
    assert lectura_impacto(filas, "KO", 0.25, 0.15) == [
        ("bajo", "La volatilidad anual de la cartera bajó de 30,0 % a 25,0 %: la operación diversificó.")
    ]
