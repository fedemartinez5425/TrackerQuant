from datetime import date
from unittest.mock import patch

from core.portfolio.portfolio_engine import calcular_tenencias, construir_cartera
from core.storage.models import Instrumento, TipoInstrumento, Transaction, TransactionAction
from core.validation.schemas import (
    validar_no_duplicada,
    validar_venta_no_supera_tenencia,
)


def _t(ticker, accion, cantidad, precio, fecha="2024-01-01"):
    return Transaction(
        fecha=date.fromisoformat(fecha),
        ticker=ticker,
        accion=TransactionAction(accion),
        cantidad=cantidad,
        precio=precio,
    )


def test_calcular_tenencias_costo_promedio():
    txs = [
        _t("AAPL", "COMPRA", 10, 100, "2024-01-01"),
        _t("AAPL", "COMPRA", 10, 200, "2024-02-01"),
    ]
    tenencias = calcular_tenencias(txs)
    assert tenencias["AAPL"]["cantidad"] == 20
    assert tenencias["AAPL"]["costo_total"] == 10 * 100 + 10 * 200


def test_calcular_tenencias_con_venta_reduce_proporcional():
    txs = [
        _t("AAPL", "COMPRA", 10, 100, "2024-01-01"),
        _t("AAPL", "VENTA", 5, 150, "2024-02-01"),
    ]
    tenencias = calcular_tenencias(txs)
    assert tenencias["AAPL"]["cantidad"] == 5
    # costo promedio se mantiene en 100 (no afectado por precio de venta)
    assert tenencias["AAPL"]["costo_total"] == 5 * 100


def test_posicion_cerrada_no_aparece():
    txs = [
        _t("AAPL", "COMPRA", 10, 100, "2024-01-01"),
        _t("AAPL", "VENTA", 10, 150, "2024-02-01"),
    ]
    tenencias = calcular_tenencias(txs)
    assert "AAPL" not in tenencias


@patch("core.portfolio.portfolio_engine.data_providers.get_price", return_value=180.0)
def test_construir_cartera_calcula_peso_y_ganancia(mock_price):
    txs = [
        _t("AAPL", "COMPRA", 10, 100, "2024-01-01"),
        _t("MSFT", "COMPRA", 5, 300, "2024-01-01"),
    ]
    posiciones = construir_cartera(txs)
    assert len(posiciones) == 2
    total_peso = sum(p.peso for p in posiciones)
    assert abs(total_peso - 1.0) < 1e-9
    aapl = next(p for p in posiciones if p.ticker == "AAPL")
    assert aapl.ganancia_perdida == (10 * 180.0) - (10 * 100.0)


def test_validar_venta_no_supera_tenencia_detecta_sobreventa():
    existentes = [_t("AAPL", "COMPRA", 5, 100)]
    venta = _t("AAPL", "VENTA", 10, 150)
    resultado = validar_venta_no_supera_tenencia(venta, existentes)
    assert not resultado.ok
    assert "solo tenés 5" in resultado.errores[0]


def test_validar_no_duplicada_detecta_duplicado_exacto():
    existentes = [_t("AAPL", "COMPRA", 10, 100, "2024-01-01")]
    nueva = _t("AAPL", "COMPRA", 10, 100, "2024-01-01")
    resultado = validar_no_duplicada(nueva, existentes)
    assert not resultado.ok


@patch("core.portfolio.portfolio_engine.data_providers.get_price")
def test_construir_cartera_usa_instrumento_dimension_para_cedear(mock_price):
    """El ratio/ticker_usd ya no vive en la transacción -- se busca en la
    tabla dimensión `instrumentos`, pasada como dict al motor de cartera."""
    precios = {"AMZN.BA": 3100.0, "AMZN": 220.0}
    mock_price.side_effect = lambda ticker, use_cache=True: precios.get(ticker)

    txs = [_t("AMZN", "COMPRA", 10, 2500, "2024-01-01")]
    instrumentos = {
        "AMZN": Instrumento(ticker="AMZN", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="AMZN", ratio_cedear=144.0)
    }

    with patch("core.portfolio.portfolio_engine.get_ccl_automatico", return_value={"valor": 1000.0, "fuente": "test"}):
        posiciones = construir_cartera(txs, instrumentos)

    amzn = posiciones[0]
    assert amzn.tipo_instrumento == TipoInstrumento.CEDEAR
    assert amzn.precio_bcba == 3100.0
    # precio teórico = (220 / 144) * 1000 = 1527.78
    assert round(amzn.precio_teorico, 2) == 1527.78
    assert amzn.precio_final == 3100.0  # usa BCBA cuando está disponible
