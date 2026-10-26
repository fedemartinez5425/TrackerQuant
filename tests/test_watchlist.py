"""Watchlist: modelo, CsvRepository en tmp_path y SheetsRepository con hoja falsa (sin red)."""
import pytest

from core.storage import sheets_repository as sr
from core.storage.csv_repository import WATCHLIST_FIELDS, CsvRepository
from core.storage.models import TipoInstrumento, WatchlistItem


class HojaFalsa:
    def __init__(self, headers):
        self.values = [list(headers)]
        self.lecturas = 0

    def get_all_values(self):
        self.lecturas += 1
        return [list(r) for r in self.values]

    def append_row(self, fila):
        self.values.append(list(fila))

    def append_rows(self, filas):
        self.values.extend(list(f) for f in filas)

    def update(self, range_name, values):
        fila = int(range_name.split(":")[0][1:])
        self.values[fila - 1] = list(values[0])

    def delete_rows(self, fila):
        del self.values[fila - 1]


def _csv_repo(tmp_path):
    # Sin watchlist_file: el parámetro es opcional y cae junto a transactions.csv.
    return CsvRepository(
        transactions_file=tmp_path / "transactions.csv",
        audit_file=tmp_path / "audit_log.csv",
        snapshots_file=tmp_path / "portfolio_snapshots.csv",
        instrumentos_file=tmp_path / "instrumentos.csv",
        processed_files_file=tmp_path / "processed_files.csv",
        forecasts_file=tmp_path / "forecast_log.csv",
    )


def _sheets_repo():
    repo = object.__new__(sr.SheetsRepository)
    repo._cache_filas = {}
    repo._worksheets = {sr.SHEET_WATCHLIST: HojaFalsa(WATCHLIST_FIELDS)}
    return repo


def _meta(notas=""):
    return WatchlistItem(ticker="meta", ticker_usd="meta", ratio_cedear=24, notas=notas)


def test_modelo_valida_y_roundtrip():
    item = _meta("ads")
    assert item.ticker == "META" and item.ticker_usd == "META"
    assert WatchlistItem.from_row(item.to_row()) == item

    accion = WatchlistItem(ticker="ggal", tipo_instrumento=TipoInstrumento.ACCION_ARG)
    assert accion.ratio_cedear is None

    with pytest.raises(ValueError):
        WatchlistItem(ticker="X")  # CEDEAR sin ticker_usd
    with pytest.raises(ValueError):
        WatchlistItem(ticker="GGAL", tipo_instrumento=TipoInstrumento.ACCION_ARG, ratio_cedear=10)


def test_from_row_tolera_vacios():
    item = WatchlistItem.from_row({"ticker": "AAPL", "ticker_usd": "AAPL", "ratio_cedear": "", "agregado_en": ""})
    assert item.ratio_cedear is None and item.notas == ""
    assert item.tipo_instrumento == TipoInstrumento.CEDEAR


def test_csv_upsert_list_remove(tmp_path):
    repo = _csv_repo(tmp_path)
    assert (tmp_path / "watchlist.csv").exists()
    assert repo.list_watchlist() == []

    repo.upsert_watchlist_item(_meta())
    repo.upsert_watchlist_item(WatchlistItem(ticker="GGAL", tipo_instrumento=TipoInstrumento.ACCION_ARG))
    repo.upsert_watchlist_item(_meta("actualizado"))  # mismo ticker: reemplaza, no duplica

    items = {i.ticker: i for i in repo.list_watchlist()}
    assert set(items) == {"META", "GGAL"}
    assert items["META"].notas == "actualizado"

    assert repo.remove_watchlist_item("meta") is True
    assert repo.remove_watchlist_item("META") is False
    assert [i.ticker for i in repo.list_watchlist()] == ["GGAL"]


def test_sheets_upsert_list_remove():
    repo = _sheets_repo()
    hoja = repo._worksheets[sr.SHEET_WATCHLIST]

    repo.upsert_watchlist_item(_meta())
    repo.upsert_watchlist_item(_meta("actualizado"))
    assert len(hoja.values) == 2  # header + 1 fila: el segundo upsert actualizó
    assert repo.list_watchlist()[0].notas == "actualizado"

    lecturas = hoja.lecturas
    repo.list_watchlist()
    assert hoja.lecturas == lecturas  # cacheado

    assert repo.remove_watchlist_item("META") is True
    assert repo.list_watchlist() == []  # la baja invalidó el cache
    assert repo.remove_watchlist_item("META") is False
