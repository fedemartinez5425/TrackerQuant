import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configura logging una sola vez para toda la app."""
    root = logging.getLogger()
    if root.handlers:
        return  # ya configurado (evita duplicar handlers en reruns de Streamlit)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level)
