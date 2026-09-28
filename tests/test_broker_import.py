from datetime import date

from core.importers.broker_movimientos import (
    extraer_ticker_y_tipo,
    parsear_fecha_ar,
    parsear_movimientos_csv,
    parsear_numero_ar,
)
from core.importers.portfolio_report import parsear_portfolio_report_csv, reconciliar
from core.storage.models import TipoInstrumento, TransactionAction

CSV_MOVIMIENTOS = (
    "nroTicket;nroComprobante;fechaEjecucion;fechaLiquidacion;tipoOperacion;instrumento;"
    "moneda;mercado;cantidad;precio;montoBruto;comision;ddmm;iva;otros;total\n"
    "88163073;6333766;04-02-2026;04-02-2026;Recibo De Cobro;;ARS;;;;1.500;0;0;0;0;1.500\n"
    "88458490;971320;04-02-2026;04-02-2026;Liquidacion Suscripcion Fci;"
    "FCI COCOS PESOS PLUS CL.A $ (COCOSPPA);ARS;;1.191,666;1.258,742;-1.500;0;0;0;0;-1.500\n"
    "100175156;2730105;06-04-2026;07-04-2026;Compra;CEDEAR AMAZON.COM, INC (AMZN);ARS;BYMA;"
    "1;2.190;-2.190;-9,855;-1,095;-2,2995;0;-2.203,25\n"
    "102455002;3077717;20-04-2026;20-04-2026;Venta;CEDEAR AMAZON.COM, INC (AMZN);ARS;BYMA;"
    "-2;2.502,5;5.005;-22,5225;-2,5025;-5,2553;0;4.974,72\n"
    "111080593;4577632;25-06-2026;26-06-2026;Compra;BOLSAS Y MERCADOS ARG. $ ORD. (BYMA) (BYMA);"
    "ARS;BYMA;4;307;-1.228;-5,526;-0,614;-1,2894;0;-1.235,43\n"
    "115631001;5278670;29-07-2026;30-07-2026;Compra;PAMPA ENERGIA S.A. ESCRIT.  1 VOTO (PAMP);"
    "ARS;BYMA;1;5.375;-5.375;-24,1875;-2,6875;-5,6438;0;-5.407,52\n"
)

CSV_PORTFOLIO = (
    "instrumento;cantidad;precio;moneda;total\n"
    "CEDEAR BIOCERES CROP SOLUTIONS CORP. (BIOX);16;685;ARS;10960\n"
    "CEDEAR AMAZON.COM, INC (AMZN);8;2860;ARS;22880\n"
    "PAMPA ENERGIA S.A. ESCRIT.  1 VOTO (PAMP);3;5385;ARS;16155\n"
    "ARS;134,27;1;ARS;134,27\n"
    "USD;0,02;1;USD;0,02\n"
)


def test_parsear_numero_ar():
    assert parsear_numero_ar("1.500") == 1500.0
    assert parsear_numero_ar("1.191,666") == 1191.666
    assert parsear_numero_ar("-2.378,80") == -2378.80
    assert parsear_numero_ar("") is None
    assert parsear_numero_ar(None) is None


def test_parsear_fecha_ar():
    assert parsear_fecha_ar("04-02-2026") == date(2026, 2, 4)
    assert parsear_fecha_ar("") is None


def test_extraer_ticker_y_tipo_cedear():
    resultado = extraer_ticker_y_tipo("CEDEAR AMAZON.COM, INC (AMZN)")
    assert resultado == ("AMZN", TipoInstrumento.CEDEAR)


def test_extraer_ticker_y_tipo_accion_directa():
    resultado = extraer_ticker_y_tipo("PAMPA ENERGIA S.A. ESCRIT.  1 VOTO (PAMP)")
    assert resultado == ("PAMP", TipoInstrumento.ACCION_ARG)


def test_extraer_ticker_y_tipo_doble_parentesis():
    resultado = extraer_ticker_y_tipo("BOLSAS Y MERCADOS ARG. $ ORD. (BYMA) (BYMA)")
    assert resultado == ("BYMA", TipoInstrumento.ACCION_ARG)


def test_extraer_ticker_y_tipo_no_soportado():
    assert extraer_ticker_y_tipo("FCI COCOS PESOS PLUS CL.A $ (COCOSPPA)") is None
    assert extraer_ticker_y_tipo("") is None


def test_parsear_movimientos_csv_filtra_y_extrae_correctamente():
    resultado = parsear_movimientos_csv(CSV_MOVIMIENTOS)

    # Recibo De Cobro y FCI se omiten (no son compra/venta de acciones)
    assert len(resultado.omitidos) == 2
    assert len(resultado.candidatos) == 4

    compra_amzn = next(c for c in resultado.candidatos if c.ticker == "AMZN" and c.accion == TransactionAction.COMPRA)
    assert compra_amzn.tipo_instrumento == TipoInstrumento.CEDEAR
    assert compra_amzn.ticker_usd == "AMZN"
    assert compra_amzn.cantidad == 1
    assert compra_amzn.precio == 2190.0
    assert compra_amzn.id_externo == "100175156"

    venta_amzn = next(c for c in resultado.candidatos if c.ticker == "AMZN" and c.accion == TransactionAction.VENTA)
    assert venta_amzn.cantidad == 2  # siempre positiva, la dirección la da 'accion'

    pamp = next(c for c in resultado.candidatos if c.ticker == "PAMP")
    assert pamp.tipo_instrumento == TipoInstrumento.ACCION_ARG
    assert pamp.ratio_cedear is None
    assert pamp.ticker_usd is None


def test_parsear_movimientos_csv_respeta_ids_ya_importados():
    resultado = parsear_movimientos_csv(CSV_MOVIMIENTOS, ids_externos_existentes={"100175156"})
    assert "100175156" in resultado.ya_importados
    assert not any(c.id_externo == "100175156" for c in resultado.candidatos)


def test_parsear_portfolio_report_separa_efectivo_de_posiciones():
    resultado = parsear_portfolio_report_csv(CSV_PORTFOLIO)
    assert len(resultado.posiciones) == 3
    assert resultado.saldo_efectivo["ARS"] == 134.27
    assert resultado.saldo_efectivo["USD"] == 0.02

    amzn = next(p for p in resultado.posiciones if p.ticker == "AMZN")
    assert amzn.cantidad == 8
    assert amzn.tipo_instrumento == TipoInstrumento.CEDEAR


def test_reconciliar_detecta_diferencias():
    from dataclasses import dataclass

    @dataclass
    class PosicionFake:
        ticker: str
        cantidad: float

    posiciones_app = [PosicionFake("AMZN", 5), PosicionFake("PAMP", 3)]
    resultado = parsear_portfolio_report_csv(CSV_PORTFOLIO)  # AMZN=8, PAMP=3, BIOX=16 en el broker

    filas = reconciliar(resultado.posiciones, posiciones_app)
    fila_amzn = next(f for f in filas if f["Ticker"] == "AMZN")
    assert fila_amzn["Coincide"] == "⚠️"
    assert fila_amzn["Diferencia"] == -3  # app tiene 5, broker dice 8

    fila_pamp = next(f for f in filas if f["Ticker"] == "PAMP")
    assert fila_pamp["Coincide"] == "✅"

    fila_biox = next(f for f in filas if f["Ticker"] == "BIOX")
    assert fila_biox["Cantidad (app, desde transacciones)"] == 0  # no está en el log de la app todavía
