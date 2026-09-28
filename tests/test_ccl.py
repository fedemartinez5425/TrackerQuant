from unittest.mock import patch

from core.data_providers import ccl_provider


def test_ccl_automatico_usa_el_primer_par_disponible():
    precios = {"GGAL.BA": 5000.0, "GGAL": 50.0}

    def fake_price(ticker, use_cache=True):
        return precios.get(ticker)

    ccl_provider._ccl_cache = None  # reset cache entre tests
    with patch("core.data_providers.get_price", side_effect=fake_price):
        resultado = ccl_provider.get_ccl_automatico(use_cache=False)

    assert resultado is not None
    # CCL = (precio_ARS * ratio) / precio_USD = (5000 * 10) / 50 = 1000
    assert resultado["valor"] == 1000.0
    assert "GGAL.BA/GGAL" in resultado["fuente"]


def test_ccl_automatico_cae_al_segundo_par_si_el_primero_falla():
    precios = {"YPFD.BA": 3000.0, "YPF": 30.0}  # GGAL.BA/GGAL sin datos

    def fake_price(ticker, use_cache=True):
        return precios.get(ticker)

    ccl_provider._ccl_cache = None
    with patch("core.data_providers.get_price", side_effect=fake_price):
        resultado = ccl_provider.get_ccl_automatico(use_cache=False)

    assert resultado is not None
    assert "YPFD.BA/YPF" in resultado["fuente"]


def test_ccl_automatico_devuelve_none_si_ningun_par_tiene_datos():
    ccl_provider._ccl_cache = None
    with patch("core.data_providers.get_price", return_value=None):
        resultado = ccl_provider.get_ccl_automatico(use_cache=False)
    assert resultado is None
