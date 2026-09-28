from datetime import date

import pytest
from pydantic import ValidationError

from core.portfolio.portfolio_engine import calcular_tenencias_a_fecha
from core.storage.models import Currency, Instrumento, TipoInstrumento, Transaction, TransactionAction


def test_cedear_requiere_ratio_y_ticker_usd():
    with pytest.raises(ValidationError):
        Instrumento(ticker="AMZN", tipo_instrumento=TipoInstrumento.CEDEAR)  # falta ratio y ticker_usd


def test_accion_arg_no_puede_tener_ratio():
    with pytest.raises(ValidationError):
        Instrumento(ticker="PAMP", tipo_instrumento=TipoInstrumento.ACCION_ARG, ratio_cedear=25.0)


def test_cedear_valido_con_ratio_y_ticker_usd():
    inst = Instrumento(ticker="AMZN", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="AMZN", ratio_cedear=144.0)
    assert inst.ratio_cedear == 144.0


def test_accion_arg_directa_valida_sin_ratio():
    inst = Instrumento(ticker="PAMP")
    assert inst.tipo_instrumento == TipoInstrumento.ACCION_ARG
    assert inst.ratio_cedear is None


def test_transaction_ya_no_lleva_metadata_de_instrumento():
    """La Transaction (tabla de hechos) es simple: no repite tipo/ratio/ADR,
    eso vive en la tabla dimensión Instrumento."""
    tx = Transaction(
        fecha=date(2024, 1, 1), ticker="PAMP", accion=TransactionAction.COMPRA,
        cantidad=3, precio=5216.66, moneda=Currency.ARS,
    )
    assert not hasattr(tx, "tipo_instrumento")
    assert not hasattr(tx, "ratio_cedear")


def test_calcular_tenencias_a_fecha_excluye_compras_posteriores():
    txs = [
        Transaction(fecha=date(2024, 1, 1), ticker="PAMP", accion=TransactionAction.COMPRA, cantidad=10, precio=100),
        Transaction(fecha=date(2024, 6, 1), ticker="PAMP", accion=TransactionAction.COMPRA, cantidad=5, precio=150),
    ]
    tenencias_marzo = calcular_tenencias_a_fecha(txs, date(2024, 3, 1))
    assert tenencias_marzo["PAMP"]["cantidad"] == 10  # todavía no había pasado la 2da compra

    tenencias_julio = calcular_tenencias_a_fecha(txs, date(2024, 7, 1))
    assert tenencias_julio["PAMP"]["cantidad"] == 15
