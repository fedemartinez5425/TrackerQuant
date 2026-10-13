"""
Uso:
    python scripts/generar_credenciales.py

Te pregunta usuario, nombre, email y contraseña, y actualiza (o crea)
config/credentials.yaml con la contraseña ya hasheada con bcrypt.
Además imprime el bloque listo para pegar en los Secrets de Streamlit Cloud
(usuario + cookie con una clave aleatoria nueva).
Ejecutalo desde la raíz del proyecto.
"""
import getpass
import secrets
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
            "cookie": {"name": "tracker_riesgo_auth", "key": settings.COOKIE_KEY or secrets.token_hex(32), "expiry_days": 1},
        }

    username = input("Usuario (sin espacios, ej: fede): ").strip()
    nombre = input("Nombre para mostrar: ").strip()
    email = input("Email: ").strip()
    password = getpass.getpass("Contraseña: ")

    if len(password) < 8:
        print("La contraseña debe tener al menos 8 caracteres.")
        sys.exit(1)
    if getpass.getpass("Repetí la contraseña: ") != password:
        print("Las contraseñas no coinciden.")
        sys.exit(1)

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
    print(
        "\n" + "=" * 70 + "\n"
        "Para Streamlit Cloud: copiá TODO lo que está entre las líneas y pegalo\n"
        "al FINAL de Settings -> Secrets de tu app (después de lo que ya tenés).\n"
        "Si ya tenés una sección [cookie], no la dupliques: pegá solo [credentials...].\n"
        + "=" * 70 + "\n"
        f"[credentials.usernames.{username}]\n"
        f"name = \"{nombre}\"\n"
        f"email = \"{email}\"\n"
        f"password = \"{hashed}\"\n"
        "\n"
        "[cookie]\n"
        "name = \"tracker_riesgo_auth\"\n"
        f"key = \"{secrets.token_hex(32)}\"\n"
        "expiry_days = 30\n"
        + "=" * 70
    )


if __name__ == "__main__":
    main()
