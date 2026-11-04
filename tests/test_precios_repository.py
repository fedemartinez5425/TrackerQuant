"""Pestaña `precios` (almacén que llena el ETL) en CSV y en Sheets (hoja falsa, sin red)."""
from datetime import date, datetime, timezone

from core.storage import sheets_repository as sr
from core.storage.csv_repository import PRECIO_FIELDS, CsvRepository
from core.storage.models import PrecioCierre


def _precios(n=3, ticker="AAPL"):
    return [PrecioCierre(fecha=date(2026, 10, i + 1), ticker=ticker, close=100.123456789 + i) for i in range(n)]


def _csv(tmp_path):
    return CsvRepository(
        transactions_file=tmp_path / "t.csv", audit_file=tmp_path / "a.csv", snapshots_file=tmp_path / "s.csv",
        instrumentos_file=tmp_path / "i.csv", processed_files_file=tmp_path / "p.csv", forecasts_file=tmp_path / "f.csv",
    )


def test_csv_crea_el_archivo_con_sus_headers(tmp_path):
    repo = _csv(tmp_path)
    assert repo.precios_file.read_text(encoding="utf-8").strip() == ",".join(PRECIO_FIELDS)
    assert repo.list_precios() == []


def test_csv_reemplazar_reescribe_todo_y_conserva_la_precision(tmp_path):
    repo = _csv(tmp_path)
    repo.reemplazar_precios(_precios(5))
    repo.reemplazar_precios(_precios(2, "spy"))
    leidos = repo.list_precios()
    assert [(p.ticker, p.fecha) for p in leidos] == [("SPY", date(2026, 10, 1)), ("SPY", date(2026, 10, 2))]
    assert leidos[0].close == 100.123456789


def test_from_row_tolera_fuente_y_actualizado_vacios():
    p = PrecioCierre.from_row({"fecha": "2026-10-01", "ticker": "ggal.ba", "close": "1500.5", "fuente": "", "actualizado_en": ""})
    assert p.ticker == "GGAL.BA" and p.fuente == "yfinance" and p.actualizado_en.tzinfo == timezone.utc


class HojaPrecios:
    def __init__(self):
        self.values = [list(PRECIO_FIELDS)] + [["viejo"] * 5 for _ in range(10)]
        self.lecturas = 0
        self.llamadas = 0
        self.opciones = None

    def get_all_values(self):
        self.lecturas += 1
        return [list(r) for r in self.values]

    def resize(self, rows, cols):
        self.llamadas += 1
        self.values = (self.values + [[""] * cols] * rows)[:rows]

    def update(self, range_name, values, value_input_option=None):
        self.llamadas += 1
        assert range_name == "A1"
        self.opciones = value_input_option
        self.values[: len(values)] = [list(v) for v in values]


def _sheets():
    repo = object.__new__(sr.SheetsRepository)
    repo._cache_filas = {}
    repo._worksheets = {sr.SHEET_PRECIOS: HojaPrecios()}
    return repo


def test_sheets_reemplaza_en_dos_llamadas_y_borra_lo_que_sobra():
    repo = _sheets()
    hoja = repo._worksheets[sr.SHEET_PRECIOS]
    repo.reemplazar_precios(_precios(3))
    assert hoja.llamadas == 2
    assert hoja.opciones == "RAW"  # sin conversión regional de fechas/números
    assert len(hoja.values) == 4  # header + 3 (las 10 filas viejas se fueron)
    assert [p.close for p in repo.list_precios()] == [100.123456789, 101.123456789, 102.123456789]


def test_sheets_lectura_cacheada_e_invalidada_al_escribir():
    repo = _sheets()
    hoja = repo._worksheets[sr.SHEET_PRECIOS]
    repo.reemplazar_precios(_precios(1))
    repo.list_precios()
    repo.list_precios()
    assert hoja.lecturas == 1
    repo.reemplazar_precios(_precios(2))
    assert len(repo.list_precios()) == 2
    assert hoja.lecturas == 2


def test_to_row_usa_iso():
    fila = PrecioCierre(fecha=date(2026, 1, 2), ticker="SPY", close=1.5,
                        actualizado_en=datetime(2026, 1, 2, 21, tzinfo=timezone.utc)).to_row()
    assert fila == {"fecha": "2026-01-02", "ticker": "SPY", "close": "1.5", "fuente": "yfinance",
                    "actualizado_en": "2026-01-02T21:00:00+00:00"}
