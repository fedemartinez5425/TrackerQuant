from datetime import date

from core.importers.broker_movimientos import MovimientoCandidato
from core.importers.import_service import importar_candidatos
from core.storage.csv_repository import CsvRepository
from core.storage.models import TipoInstrumento, TransactionAction


def _repo(tmp_path):
    return CsvRepository(
        transactions_file=tmp_path / "transactions.csv",
        audit_file=tmp_path / "audit_log.csv",
        snapshots_file=tmp_path / "portfolio_snapshots.csv",
        instrumentos_file=tmp_path / "instrumentos.csv",
        processed_files_file=tmp_path / "processed_files.csv",
        forecasts_file=tmp_path / "forecast_log.csv",
    )


def test_importar_candidatos_registra_instrumento_y_transaccion(tmp_path):
    repo = _repo(tmp_path)
    candidato = MovimientoCandidato(
        id_externo="t1", fecha=date(2024, 1, 1), ticker="AMZN", tipo_instrumento=TipoInstrumento.CEDEAR,
        ticker_usd="AMZN", ratio_cedear=144.0, accion=TransactionAction.COMPRA, cantidad=7, precio=2694.71,
        comision=10.0, moneda="ARS",
    )
    resumen = importar_candidatos([candidato], repo, usuario="fede")

    assert resumen.importados == 1
    assert not resumen.errores
    assert not resumen.pendientes_de_ratio

    inst = repo.get_instrumento("AMZN")
    assert inst is not None
    assert inst.ratio_cedear == 144.0

    txs = repo.list_transactions()
    assert len(txs) == 1
    assert txs[0].id_externo == "t1"
    assert txs[0].ticker == "AMZN"


def test_importar_candidatos_cedear_sin_ratio_queda_pendiente(tmp_path):
    repo = _repo(tmp_path)
    candidato = MovimientoCandidato(
        id_externo="t2", fecha=date(2024, 1, 1), ticker="GLOB", tipo_instrumento=TipoInstrumento.CEDEAR,
        ticker_usd="GLOB", ratio_cedear=None, accion=TransactionAction.COMPRA, cantidad=4, precio=1000.0,
        comision=0.0, moneda="ARS",
    )
    resumen = importar_candidatos([candidato], repo, usuario="fede")

    assert resumen.importados == 0
    assert resumen.pendientes_de_ratio == ["GLOB"]
    assert repo.list_transactions() == []


def test_importar_candidatos_usa_ratio_override(tmp_path):
    repo = _repo(tmp_path)
    candidato = MovimientoCandidato(
        id_externo="t3", fecha=date(2024, 1, 1), ticker="GLOB", tipo_instrumento=TipoInstrumento.CEDEAR,
        ticker_usd="GLOB", ratio_cedear=None, accion=TransactionAction.COMPRA, cantidad=4, precio=1000.0,
        comision=0.0, moneda="ARS",
    )
    resumen = importar_candidatos([candidato], repo, usuario="fede", ratios_override={"GLOB": 2.0})

    assert resumen.importados == 1
    assert repo.get_instrumento("GLOB").ratio_cedear == 2.0


def test_importar_candidatos_no_redefine_instrumento_ya_existente(tmp_path):
    repo = _repo(tmp_path)
    c1 = MovimientoCandidato(
        id_externo="a", fecha=date(2024, 1, 1), ticker="PAMP", tipo_instrumento=TipoInstrumento.ACCION_ARG,
        ticker_usd=None, ratio_cedear=None, accion=TransactionAction.COMPRA, cantidad=1, precio=100.0,
        comision=0.0, moneda="ARS",
    )
    c2 = MovimientoCandidato(
        id_externo="b", fecha=date(2024, 2, 1), ticker="PAMP", tipo_instrumento=TipoInstrumento.ACCION_ARG,
        ticker_usd=None, ratio_cedear=None, accion=TransactionAction.COMPRA, cantidad=2, precio=110.0,
        comision=0.0, moneda="ARS",
    )
    resumen = importar_candidatos([c1, c2], repo, usuario="fede")
    assert resumen.importados == 2
    assert len(repo.list_instrumentos()) == 1  # PAMP solo se registró una vez
