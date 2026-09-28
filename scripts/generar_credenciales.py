"""
Uso:
    python scripts/generar_credenciales.py

Te pregunta usuario, nombre, email y contraseña, y actualiza (o crea)
config/credentials.yaml con la contraseña ya hasheada con bcrypt.
Ejecutalo desde la raíz del proyecto.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit_authenticator as stauth  # noqa: E402
import yaml  # noqa: E402
from yaml.loader import SafeLoader  # noqa: E402

from config.settings import settings  # noqa: E402


def main():
    path = settings.AUTH_CREDENTIALS_FILE
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            config = yaml.load(f, Loader=SafeLoader)
    else:
        config = {
            "credentials": {"usernames": {}},
            "cookie": {"name": "tracker_cuantitativo_auth", "key": settings.COOKIE_KEY, "expiry_days": 1},
        }

    username = input("Usuario (sin espacios, ej: fede): ").strip()
    nombre = input("Nombre para mostrar: ").strip()
    email = input("Email: ").strip()
    password = getpass.getpass("Contraseña: ")

    hashed = stauth.Hasher([password]).generate()[0]
    config["credentials"]["usernames"][username] = {
        "name": nombre,
        "email": email,
        "password": hashed,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(config, f)

    print(f"\nUsuario '{username}' guardado en {path}")


if __name__ == "__main__":
    main()
