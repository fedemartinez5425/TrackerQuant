from core.importers.drive_sync import detectar_tipo_archivo


def test_detecta_movimientos_por_columna_nroticket():
    contenido = "nroTicket;nroComprobante;fechaEjecucion;tipoOperacion;instrumento;cantidad;precio\n1;2;3;Compra;AMZN;1;100"
    assert detectar_tipo_archivo(contenido) == "movimientos"


def test_detecta_portfolio_report_por_columnas():
    contenido = "instrumento;cantidad;precio;moneda;total\nAMZN;8;2860;ARS;22880"
    assert detectar_tipo_archivo(contenido) == "portfolio_report"


def test_detecta_desconocido_si_no_matchea():
    contenido = "col_a;col_b\n1;2"
    assert detectar_tipo_archivo(contenido) == "desconocido"


def test_detecta_vacio_como_desconocido():
    assert detectar_tipo_archivo("") == "desconocido"
