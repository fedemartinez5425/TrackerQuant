"""
Autenticación de sistema cerrado: no hay registro público.

Dos fuentes de configuración posibles (en este orden de prioridad):
  1. st.secrets["credentials"] / st.secrets["cookie"] -- para Streamlit
     Community Cloud, pegado en el panel de Secrets, nunca en el repo.
  2. config/credentials.yaml local (generado con
     scripts/generar_credenciales.py, que hashea la contraseña con bcrypt)
     -- para desarrollo local.

Usa streamlit-authenticator, que maneja cookies de sesión y logout.
"""
from __future__ import annotations

import logging

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

from config.settings import settings
from core.cloud_secrets import get_secret

logger = logging.getLogger(__name__)

DEFAULT_CREDENTIALS_TEMPLATE = {
    "credentials": {
        "usernames": {
            "admin": {
                "name": "Admin",
                "password": "",  # se completa con un hash real en _cargar_o_crear_config()
                "email": "admin@example.com",
            }
        }
    },
    "cookie": {
        "name": "tracker_riesgo_auth",
        "key": settings.COOKIE_KEY,
        "expiry_days": 1,
    },
}


def _cargar_desde_secrets() -> dict | None:
    """Si hay credenciales en st.secrets (Streamlit Cloud), las usa directo
    -- nunca toca el filesystem (que en Cloud es efímero de todos modos)."""
    credenciales = get_secret(["credentials"])
    cookie = get_secret(["cookie"])
    if not credenciales:
        return None
    return {
        "credentials": dict(credenciales),
        "cookie": dict(cookie) if cookie else DEFAULT_CREDENTIALS_TEMPLATE["cookie"],
    }


def _cargar_o_crear_config_local() -> dict:
    path = settings.AUTH_CREDENTIALS_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Genera un hash real por defecto para que la app funcione
        # out-of-the-box: usuario "admin" / clave "cambiar123"
        hashed = stauth.Hasher(["cambiar123"]).generate()[0]
        config = {
            "credentials": {"usernames": {"admin": {**DEFAULT_CREDENTIALS_TEMPLATE["credentials"]["usernames"]["admin"], "password": hashed}}},
            "cookie": DEFAULT_CREDENTIALS_TEMPLATE["cookie"],
        }
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(config, f)
        logger.info("Se creó config/credentials.yaml con usuario admin por defecto.")
    with path.open("r", encoding="utf-8") as f:
        return yaml.load(f, Loader=SafeLoader)


def get_authenticator() -> stauth.Authenticate:
    config = _cargar_desde_secrets() or _cargar_o_crear_config_local()
    return stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )


def render_login() -> tuple[bool, str | None]:
    """Muestra el formulario de login. Devuelve (autenticado, usuario)."""
    authenticator = get_authenticator()
    authenticator.login(location="main")

    auth_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

    if auth_status is False:
        st.error("Usuario o contraseña incorrectos.")
    elif auth_status is None:
        usando_secrets = _cargar_desde_secrets() is not None
        if usando_secrets:
            st.info("Ingresá tus credenciales para continuar.")
        else:
            st.info(
                "Ingresá tus credenciales para continuar. (Usuario por defecto: **admin** / "
                "clave: **cambiar123** — cambiala con `python scripts/generar_credenciales.py`)"
            )

    if auth_status:
        st.session_state["authenticator"] = authenticator
        return True, username
    return False, None


def render_logout_button() -> None:
    authenticator = st.session_state.get("authenticator")
    if authenticator:
        authenticator.logout("Cerrar sesión", "sidebar")
