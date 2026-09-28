from io import BytesIO

import openpyxl
import pytest

from core.data_providers.comafi_ratios import _parsear_ratio, parsear_workbook


def _crear_xlsx_sintetico() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Shares"
    ws.append(["CEDEARS Shares"])  # fila de título, se debe ignorar
    ws.append([
        "Identificación Mercado", "Denominación del programa", "País de Origen",
        "Código Caja de Valores", "ISIN CEDEAR", "ISIN Subyacente",
        "Valor Subyacente", "Ratio Cedear / Acción ó ADR", "Montos Máximos",
    ])
    ws.append(["AMZN", "Amazon.com Inc", "Estados Unidos", "X", "X", "X", "X", "144 a 1", "X"])
    ws.append(["AAPL", "Apple Inc", "Estados Unidos", "X", "X", "X", "X", "20:1", "X"])
    ws.append(["MELI", "MercadoLibre Inc", "Estados Unidos", "X", "X", "X", "X", "2", "X"])

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_parsear_ratio_formatos_variados():
    assert _parsear_ratio("144 a 1") == 144.0
    assert _parsear_ratio("20:1") == 20.0
    assert _parsear_ratio("9 x 1") == 9.0
    assert _parsear_ratio("2") == 2.0
    assert _parsear_ratio(10) == 10.0
    assert _parsear_ratio(None) is None
    assert _parsear_ratio("") is None


def test_parsear_workbook_extrae_tickers_y_ratios():
    contenido = _crear_xlsx_sintetico()
    df = parsear_workbook(contenido)

    assert not df.empty
    assert set(df["ticker"]) == {"AMZN", "AAPL", "MELI"}

    fila_amzn = df[df["ticker"] == "AMZN"].iloc[0]
    assert fila_amzn["ratio"] == 144.0

    fila_aapl = df[df["ticker"] == "AAPL"].iloc[0]
    assert fila_aapl["ratio"] == 20.0

    fila_meli = df[df["ticker"] == "MELI"].iloc[0]
    assert fila_meli["ratio"] == 2.0


def test_parsear_workbook_sin_columna_ratio_devuelve_vacio():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Esto", "No tiene", "Las columnas esperadas"])
    ws.append(["a", "b", "c"])
    buffer = BytesIO()
    wb.save(buffer)

    df = parsear_workbook(buffer.getvalue())
    assert df.empty
