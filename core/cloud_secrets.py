"""
Puente hacia st.secrets, aislado en un solo módulo para que el resto del
código (config/settings.py incluido) siga siendo Python puro y testeable
sin necesidad de correr dentro de Streamlit.

En local: st.secrets no existe (no hay secrets.toml) -> todo cae a los
archivos/env locales de siempre.
En Streamlit Community Cloud: las credenciales se pegan en el panel de
"Secrets" de la app (nunca en el repo de GitHub) y este módulo las expone.
"""
from __future__ import annotations

from typing import Any


def get_secret(path: list[str], default: Any = None) -> Any:
    """Busca st.secrets["a"]["b"]... siguiendo `path`. Si Streamlit no está
    corriendo, no hay secrets.toml, o falta la clave, devuelve `default`
    sin levantar excepción -- nunca debe romper un import ni un test."""
    try:
        import streamlit as st

        node: Any = st.secrets
        for key in path:
            node = node[key]
        return node
    except Exception:  # noqa: BLE001 - cualquier fallo acá cae al default
        return default


def secrets_disponibles() -> bool:
    """True si hay un st.secrets con contenido (estamos en Cloud o hay
    un .streamlit/secrets.toml local)."""
    try:
        import streamlit as st

        return len(st.secrets) > 0
    except Exception:  # noqa: BLE001
        return False
