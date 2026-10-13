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


# construir_cartera arma el CCL histórico (red); en estos tests no interesa el USD.
_SIN_CCL_HISTORICO = patch("core.portfolio.portfolio_engine.tipo_cambio_ccl_historico", new=lambda: (lambda f: None))


@_SIN_CCL_HISTORICO
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


@_SIN_CCL_HISTORICO
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


# ---------------- G/P en USD-CCL ----------------
from core.portfolio.portfolio_engine import resumen_cartera  # noqa: E402
from core.storage.models import Currency  # noqa: E402

CCL_POR_FECHA = {date(2024, 1, 1): 1000.0, date(2024, 6, 1): 1250.0, date(2024, 9, 1): 1300.0}


def _fx(fecha):
    return CCL_POR_FECHA.get(fecha)


def test_costo_usd_compras_en_pesos_al_ccl_de_su_fecha():
    txs = [
        _t("GGAL", "COMPRA", 10, 1000, "2024-01-01"),  # $10.000 / 1000 = US$ 10
        _t("GGAL", "COMPRA", 10, 2500, "2024-06-01"),  # $25.000 / 1250 = US$ 20
    ]
    tenencias = calcular_tenencias(txs, fx_usd_ars=_fx)
    assert tenencias["GGAL"]["costo_total"] == 35_000
    assert tenencias["GGAL"]["costo_total_usd"] == 30.0


def test_costo_usd_compra_en_dolares_se_toma_directo_con_comision():
    t = Transaction(
        fecha=date(2024, 6, 1), ticker="AAPL", accion=TransactionAction.COMPRA,
        cantidad=2, precio=10, moneda=Currency.USD, comision=1,
    )
    tenencias = calcular_tenencias([t], fx_usd_ars=_fx)
    assert tenencias["AAPL"]["costo_total_usd"] == 21.0
    assert tenencias["AAPL"]["costo_total"] == 21.0 * 1250


def test_venta_descuenta_costo_usd_a_costo_promedio():
    txs = [
        _t("GGAL", "COMPRA", 10, 1000, "2024-01-01"),  # US$ 10
        _t("GGAL", "COMPRA", 10, 2500, "2024-06-01"),  # US$ 20
        _t("GGAL", "VENTA", 5, 9999, "2024-09-01"),  # precio de venta no afecta el costo
    ]
    tenencias = calcular_tenencias(txs, fx_usd_ars=_fx)
    assert tenencias["GGAL"]["cantidad"] == 15
    assert tenencias["GGAL"]["costo_total_usd"] == 30.0 * 15 / 20
    assert tenencias["GGAL"]["costo_total"] == 35_000 * 15 / 20


def test_sin_ccl_de_la_compra_el_costo_usd_queda_sin_dato():
    txs = [_t("GGAL", "COMPRA", 10, 1000, "2024-01-01"), _t("GGAL", "COMPRA", 1, 1000, "2024-02-15")]
    tenencias = calcular_tenencias(txs, fx_usd_ars=_fx)
    assert tenencias["GGAL"]["costo_total_usd"] is None
    assert tenencias["GGAL"]["costo_total"] == 11_000  # el cálculo en pesos no se ve afectado
    assert calcular_tenencias(txs)["GGAL"]["costo_total_usd"] is None  # sin fx: sin dato


@patch("core.portfolio.portfolio_engine.get_ccl_automatico", return_value={"valor": 1500.0, "fuente": "test"})
@patch("core.portfolio.portfolio_engine.data_providers.get_price", return_value=4500.0)
def test_construir_cartera_calcula_gp_en_usd_y_resumen(mock_price, mock_ccl):
    txs = [
        _t("GGAL", "COMPRA", 10, 1000, "2024-01-01"),  # US$ 10
        _t("GGAL", "COMPRA", 10, 2500, "2024-06-01"),  # US$ 20
    ]
    posiciones = construir_cartera(txs, fx_usd_ars=_fx)
    ggal = posiciones[0]
    assert ggal.valor_invertido_usd == 30.0
    assert ggal.valor_actual_usd == 20 * 4500 / 1500  # US$ 60
    assert ggal.ganancia_perdida_usd == 30.0
    assert ggal.ganancia_perdida_usd_pct == 1.0

    resumen = resumen_cartera(posiciones)
    assert resumen["valor_invertido_usd_total"] == 30.0
    assert resumen["valor_actual_usd_total"] == 60.0
    assert resumen["ganancia_perdida_usd_total"] == 30.0
    assert resumen["ganancia_perdida_usd_pct_total"] == 1.0


@patch("core.portfolio.portfolio_engine.get_ccl_automatico", return_value={"valor": 1500.0, "fuente": "test"})
@patch("core.portfolio.portfolio_engine.data_providers.get_price", return_value=4500.0)
def test_resumen_sin_total_usd_si_falta_una_posicion(mock_price, mock_ccl):
    txs = [
        _t("GGAL", "COMPRA", 10, 1000, "2024-01-01"),
        _t("PAMP", "COMPRA", 10, 1000, "2024-02-15"),  # fecha sin CCL
    ]
    posiciones = construir_cartera(txs, fx_usd_ars=_fx)
    pamp = next(p for p in posiciones if p.ticker == "PAMP")
    assert pamp.ganancia_perdida_usd is None
    resumen = resumen_cartera(posiciones)
    assert resumen["ganancia_perdida_usd_total"] is None
    assert resumen["ganancia_perdida_total"] is not None
