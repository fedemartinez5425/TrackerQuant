"""Cache por ticker, recorte por período, precarga en lote y cortacircuito."""
from unittest.mock import patch

import pandas as pd
import pytest

from core import data_providers


def _serie(ticker: str, dias: int = 1000) -> pd.DataFrame:
    hoy = pd.Timestamp.today().normalize()
    idx = pd.date_range(hoy - pd.Timedelta(days=dias - 1), hoy, freq="D")
    return pd.DataFrame({ticker: range(1, len(idx) + 1)}, index=idx, dtype=float)


def test_dias_periodo():
    assert data_providers.dias_periodo("2y") == pytest.approx(730.5)
    assert data_providers.dias_periodo("6mo") == pytest.approx(182.625)
    assert data_providers.dias_periodo("5d") == 5
    assert data_providers.dias_periodo("max") == float("inf")


def test_un_pedido_de_2y_y_otro_de_3y_comparten_la_descarga():
    with patch.object(data_providers._primary, "get_history", return_value=_serie("AAA")) as mock:
        dos = data_providers.get_history("AAA", period="2y")
        tres = data_providers.get_history("AAA", period="3y")
    assert mock.call_count == 1
    assert mock.call_args.kwargs["period"] == "3y"  # se baja la ventana base
    assert len(dos) < len(tres)
    assert dos.index.min() >= pd.Timestamp.today().normalize() - pd.Timedelta(days=731)


def test_un_periodo_mas_largo_que_la_base_vuelve_a_bajar():
    with patch.object(data_providers._primary, "get_history", return_value=_serie("AAA", 2000)) as mock:
        data_providers.get_history("AAA", period="3y")
        data_providers.get_history("AAA", period="5y")
    assert mock.call_count == 2
    assert mock.call_args.kwargs["period"] == "5y"


def test_precargar_baja_en_lote_y_despues_sale_del_cache():
    lote = {"AAA": _serie("AAA"), "BBB": _serie("BBB")}
    with patch.object(data_providers._primary, "get_history_lote", return_value=lote) as mock_lote, \
            patch.object(data_providers._primary, "get_history") as mock_uno, \
            patch.object(data_providers._primary, "get_price") as mock_precio:
        data_providers.precargar(["AAA", "BBB"])
        data_providers.precargar(["AAA", "BBB"])  # ya están: no vuelve a bajar
        h = data_providers.get_history("BBB", period="1y")
        precio = data_providers.get_price("AAA")
    assert mock_lote.call_count == 1
    assert sorted(mock_lote.call_args.args[0]) == ["AAA", "BBB"]
    mock_uno.assert_not_called()
    mock_precio.assert_not_called()  # el precio es el último cierre de la historia
    assert not h.empty
    assert precio == float(lote["AAA"]["AAA"].iloc[-1])


class _ErrorDeRed(Exception):
    pass


def test_cortacircuito_tras_fallas_seguidas(monkeypatch):
    llamadas = []

    def falla(ticker, period="2y"):
        llamadas.append(ticker)
        data_providers._primary.ultimo_error = _ErrorDeRed("timeout")
        return None

    monkeypatch.setattr(data_providers._primary, "get_history", falla)
    for t in ["A", "B", "C", "D", "E"]:
        assert data_providers.get_history(t) is None
    assert llamadas == ["A", "B", "C"]  # después de 3 fallas deja de llamar
    estado = data_providers.estado_proveedores()
    assert not estado["yahoo_disponible"]
    assert "timeout" in estado["ultimo_error"]


def test_rate_limit_corta_de_inmediato(monkeypatch):
    llamadas = []

    def limitado(ticker):
        llamadas.append(ticker)
        data_providers._primary.ultimo_error = _ErrorDeRed("429 Too Many Requests")
        return None

    monkeypatch.setattr(data_providers._primary, "get_price", limitado)
    monkeypatch.setattr(type(data_providers._primary), "rate_limit", property(lambda self: True))
    data_providers.get_price("A")
    data_providers.get_price("B")
    assert llamadas == ["A"]
    assert data_providers.estado_proveedores()["pausa_restante_segundos"] > 120


def test_si_yahoo_cae_usa_la_historia_vencida(monkeypatch):
    with patch.object(data_providers._primary, "get_history", return_value=_serie("AAA")):
        data_providers.get_history("AAA", period="1y")
    monkeypatch.setattr(data_providers.settings, "PRICE_CACHE_TTL_SECONDS", -1)  # todo vencido
    with patch.object(data_providers._primary, "get_history", return_value=None):
        h = data_providers.get_history("AAA", period="1y")
    assert h is not None and not h.empty


def test_cache_acotado(monkeypatch):
    monkeypatch.setattr(data_providers, "MAX_TICKERS_EN_MEMORIA", 2)
    for t in ["A", "B", "C"]:
        data_providers._guardar_historia(t, _serie(t, 10), "3y")
    assert list(data_providers._history_cache) == ["B", "C"]
