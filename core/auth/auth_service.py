"""
Autenticación de sistema cerrado: no hay registro público.

Dos fuentes de configuración posibles (en este orden de prioridad):
  1. st.secrets["credentials"] / st.secrets["cookie"] -- para Streamlit
     Community Cloud, pegado en el panel de Secrets, nunca en el repo.
  2. config/credentials.yaml local (generado con
     scripts/generar_credenciales.py, que hashea la contraseña con bcrypt)
     -- para desarrollo local.

Usa streamlit-authenticator, que maneja cookies de sesión y logout.

Seguridad (fail-closed): si la app corre con configuración de producción
(st.secrets con storage/cuenta de servicio, es decir, Streamlit Cloud) pero
faltan las credenciales de usuarios en los Secrets, NO se crea el usuario
por defecto admin/cambiar123: la app se niega a arrancar. Antes caía al
usuario por defecto y además mostraba la clave en la pantalla de login, en
una URL pública.
"""
from __future__ import annotations

import logging
import secrets

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

from config.settings import settings
from core.cloud_secrets import get_secret, secrets_disponibles

logger = logging.getLogger(__name__)

USUARIO_DEFAULT = "admin"
CLAVE_DEFAULT = "cambiar123"

# Si no hay COOKIE_KEY configurada, una clave aleatoria por proceso: las
# sesiones se invalidan al reiniciar, pero nadie puede falsificar la cookie
# conociendo una clave por defecto publicada en el código.
_COOKIE_KEY_EFIMERA = secrets.token_hex(32)


def _cookie_key() -> str:
    return settings.COOKIE_KEY or _COOKIE_KEY_EFIMERA

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
        "key": "",  # se completa en tiempo de ejecución (ver _cookie_key)
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
    cookie_final = {**DEFAULT_CREDENTIALS_TEMPLATE["cookie"], **(_a_dict(cookie) if cookie else {})}
    if not cookie_final.get("key"):
        cookie_final["key"] = _cookie_key()
    return {"credentials": _a_dict(credenciales), "cookie": cookie_final}


def _a_dict(nodo):
    """st.secrets devuelve objetos AttrDict anidados; streamlit-authenticator
    necesita dicts comunes (y los modifica), así que se copian en profundidad."""
    if hasattr(nodo, "items"):
        return {k: _a_dict(v) for k, v in nodo.items()}
    return nodo


def _config_de_produccion() -> bool:
    """True si hay Secrets que indican un deploy real (Streamlit Cloud)."""
    if not secrets_disponibles():
        return False
    return (
        str(get_secret(["storage_backend"], "")).strip().lower() == "gsheets"
        or get_secret(["gcp_service_account"]) is not None
    )


def _cargar_o_crear_config_local() -> dict:
    path = settings.AUTH_CREDENTIALS_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Genera un hash real por defecto para que la app funcione
        # out-of-the-box: usuario "admin" / clave "cambiar123"
        hashed = stauth.Hasher([CLAVE_DEFAULT]).generate()[0]
        config = {
            "credentials": {"usernames": {USUARIO_DEFAULT: {**DEFAULT_CREDENTIALS_TEMPLATE["credentials"]["usernames"]["admin"], "password": hashed}}},
            # Clave de cookie propia y aleatoria, guardada en el yaml local (que está en .gitignore)
            "cookie": {**DEFAULT_CREDENTIALS_TEMPLATE["cookie"], "key": settings.COOKIE_KEY or secrets.token_hex(32)},
        }
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(config, f)
        logger.info("Se creó config/credentials.yaml con usuario admin por defecto.")
    with path.open("r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=SafeLoader)
    cookie = config.setdefault("cookie", dict(DEFAULT_CREDENTIALS_TEMPLATE["cookie"]))
    if not cookie.get("key") or cookie.get("key") == "tracker_riesgo_cookie_key_cambiar":
        cookie["key"] = _cookie_key()
    return config


def _clave_default_sigue_activa(config: dict) -> bool:
    """True si el usuario admin todavía tiene la clave por defecto (para
    mostrar el aviso solo en ese caso, y no publicar la clave si ya se cambió)."""
    import bcrypt

    admin = config.get("credentials", {}).get("usernames", {}).get(USUARIO_DEFAULT)
    if not admin or not admin.get("password"):
        return False
    try:
        return bcrypt.checkpw(CLAVE_DEFAULT.encode(), str(admin["password"]).encode())
    except ValueError:
        return False


def _cargar_config() -> dict:
    config = _cargar_desde_secrets()
    if config:
        return config
    if _config_de_produccion():
        st.error(
            "🔒 Faltan las credenciales de usuarios en los Secrets de la app "
            "(`[credentials.usernames.<usuario>]` y `[cookie]`, ver `.streamlit/secrets.toml.example`). "
            "Por seguridad, la app no arranca con el usuario por defecto en un deploy público."
        )
        st.stop()
    return _cargar_o_crear_config_local()


def get_authenticator() -> stauth.Authenticate:
    config = _cargar_config()
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
        config = _cargar_desde_secrets()
        if config is None and _clave_default_sigue_activa(_cargar_o_crear_config_local()):
            st.info(
                "Ingresá tus credenciales para continuar. (Usuario por defecto: **admin** / "
                "clave: **cambiar123** — cambiala con `python scripts/generar_credenciales.py`)"
            )
        else:
            st.info("Ingresá tus credenciales para continuar.")

    if auth_status:
        st.session_state["authenticator"] = authenticator
        return True, username
    return False, None


def render_logout_button() -> None:
    authenticator = st.session_state.get("authenticator")
    if authenticator:
        authenticator.logout("Cerrar sesión", "sidebar")
