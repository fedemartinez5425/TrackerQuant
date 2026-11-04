"""Fixtures comunes: los tests nunca deben salir a la red."""
import pytest


@pytest.fixture(autouse=True)
def _sin_descarga_de_comafi(monkeypatch):
    """obtener_ratio() baja el listado de Comafi si no hay cache local; en
    tests (y en CI, donde data/ está vacío) eso no debe pasar."""
    from core.data_providers import comafi_ratios

    monkeypatch.setattr(comafi_ratios, "_descarga_automatica_intentada", True)


class ProveedorSinRed:
    """Reemplaza a yfinance / Alpha Vantage: nunca devuelve datos ni sale a internet."""

    name = "sin_red"
    ultimo_error = None
    rate_limit = False

    def get_price(self, ticker):
        return None

    def get_history(self, ticker, period="2y"):
        return None

    def get_history_lote(self, tickers, period="2y"):
        return {}

    def get_info(self, ticker):
        return {}


@pytest.fixture(autouse=True)
def _proveedores_sin_red(monkeypatch):
    """Los tests que necesitan precios parchean get_price / get_history; el
    resto (ej. la precarga en lote) no debe tocar Yahoo."""
    from core import data_providers

    monkeypatch.setattr(data_providers, "_primary", ProveedorSinRed())
    monkeypatch.setattr(data_providers, "_fallback", ProveedorSinRed())
    monkeypatch.setattr(data_providers, "_cortado_hasta", 0.0)
    monkeypatch.setattr(data_providers, "_fallas_seguidas", 0)
    data_providers.almacen.configurar(None)  # sin almacén salvo que el test lo configure
    monkeypatch.setattr(data_providers.almacen, "_matriz", data_providers.almacen.pd.DataFrame())
    data_providers.limpiar_cache()
    yield
    data_providers.limpiar_cache()
