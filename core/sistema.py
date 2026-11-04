"""
Datos para la página Estado del sistema: qué versión está deployada y con
qué paquetes. Sin Streamlit ni subprocess (lee .git a mano: en Streamlit
Cloud el repo se clona con su carpeta .git, pero no siempre hay binario git).
"""
from __future__ import annotations

import platform
from importlib import metadata
from pathlib import Path

from config.settings import BASE_DIR

PAQUETES_CLAVE = ("streamlit", "streamlit-authenticator", "extra-streamlit-components", "yfinance", "pandas", "gspread")


def version_deploy(base_dir: Path = BASE_DIR) -> dict | None:
    """{'rama': 'main', 'commit': 'da828f5'} del checkout actual, o None si no hay .git."""
    git = base_dir / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref: "):
        return {"rama": None, "commit": head[:7]}  # HEAD suelto (detached)
    ref = head[5:]
    rama = ref.removeprefix("refs/heads/")
    archivo_ref = git / ref
    if archivo_ref.exists():
        return {"rama": rama, "commit": archivo_ref.read_text(encoding="utf-8").strip()[:7]}
    packed = git / "packed-refs"
    if packed.exists():
        for linea in packed.read_text(encoding="utf-8").splitlines():
            partes = linea.split()
            if len(partes) == 2 and partes[1] == ref:
                return {"rama": rama, "commit": partes[0][:7]}
    return {"rama": rama, "commit": None}


def versiones_paquetes() -> dict[str, str]:
    versiones = {"python": platform.python_version()}
    for paquete in PAQUETES_CLAVE:
        try:
            versiones[paquete] = metadata.version(paquete)
        except metadata.PackageNotFoundError:
            versiones[paquete] = "no instalado"
    return versiones
