"""SheetsRepository contra una planilla falsa en memoria (sin red):
verifica el cache de lecturas, su invalidación al escribir y el alta en lote."""
from datetime import date

from core.storage import sheets_repository as sr
from core.storage.models import Instrumento, TipoInstrumento, Transaction, TransactionAction


class HojaFalsa:
    def __init__(self, headers):
        self.values = [list(headers)]
        self.lecturas = 0
        self.escrituras = 0

    def get_all_values(self):
        self.lecturas += 1
        return [list(r) for r in self.values]

    def append_row(self, fila):
        self.escrituras += 1
        self.values.append(list(fila))

    def append_rows(self, filas):
        self.escrituras += 1
        self.values.extend(list(f) for f in filas)

    def update(self, range_name, values):
        self.escrituras += 1
        fila = int(range_name.split(":")[0][1:])
        self.values[fila - 1] = list(values[0])


def _repo():
    repo = object.__new__(sr.SheetsRepository)
    repo._cache_filas = {}
    repo._worksheets = {
        sr.SHEET_TRANSACTIONS: HojaFalsa(sr.TRANSACTION_FIELDS),
        sr.SHEET_INSTRUMENTOS: HojaFalsa(sr.INSTRUMENTO_FIELDS),
        sr.SHEET_AUDIT: HojaFalsa(sr.AUDIT_FIELDS),
    }
    return repo


def _t(cant):
    return Transaction(fecha=date(2024, 1, 1), ticker="AAPL", accion=TransactionAction.COMPRA, cantidad=cant, precio=10)


def test_lecturas_se_cachean_y_la_escritura_invalida():
    repo = _repo()
    hoja = repo._worksheets[sr.SHEET_TRANSACTIONS]
    assert repo.list_transactions() == []
    repo.list_transactions()
    assert hoja.lecturas == 1  # la segunda lectura sale del cache

    repo.add_transaction(_t(1))
    assert len(repo.list_transactions()) == 1  # la escritura invalidó el cache
    assert hoja.lecturas == 2


def test_alta_en_lote_es_una_sola_llamada():
    repo = _repo()
    hoja = repo._worksheets[sr.SHEET_TRANSACTIONS]
    repo.add_transactions([_t(1), _t(2), _t(3)])
    assert hoja.escrituras == 1
    assert [t.cantidad for t in repo.list_transactions()] == [1, 2, 3]


def test_upsert_instrumento_actualiza_en_lugar_de_duplicar():
    repo = _repo()
    repo.upsert_instrumento(Instrumento(ticker="AMZN", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="AMZN", ratio_cedear=144))
    repo.upsert_instrumento(Instrumento(ticker="AMZN", tipo_instrumento=TipoInstrumento.CEDEAR, ticker_usd="AMZN", ratio_cedear=72))
    instrumentos = repo.list_instrumentos()
    assert len(instrumentos) == 1
    assert instrumentos[0].ratio_cedear == 72


def test_reverso_funciona_igual_que_en_csv():
    repo = _repo()
    t = _t(5)
    repo.add_transaction(t)
    repo.add_reversal(t.id, "error", usuario="fede")
    from core.storage.models import transacciones_efectivas

    assert transacciones_efectivas(repo.list_transactions()) == []
