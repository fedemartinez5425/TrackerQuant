"""Fixtures comunes: los tests nunca deben salir a la red."""
import pytest


@pytest.fixture(autouse=True)
def _sin_descarga_de_comafi(monkeypatch):
    """obtener_ratio() baja el listado de Comafi si no hay cache local; en
    tests (y en CI, donde data/ está vacío) eso no debe pasar."""
    from core.data_providers import comafi_ratios

    monkeypatch.setattr(comafi_ratios, "_descarga_automatica_intentada", True)
