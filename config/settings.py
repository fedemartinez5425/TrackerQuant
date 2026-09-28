"""
Configuración central de la app.
Lee variables de entorno (.env) y valores por default.
No depende de Streamlit para poder testearse sola.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "si", "sí")


class Settings:
    # --- Rutas locales (storage por defecto = CSV, sin dependencias externas) ---
    DATA_DIR: Path = BASE_DIR / "data"
    TRANSACTIONS_FILE: Path = DATA_DIR / "transactions.csv"
    AUDIT_LOG_FILE: Path = DATA_DIR / "audit_log.csv"
    SNAPSHOTS_FILE: Path = DATA_DIR / "portfolio_snapshots.csv"
    INSTRUMENTOS_FILE: Path = DATA_DIR / "instrumentos.csv"
    PROCESSED_FILES_FILE: Path = DATA_DIR / "processed_files.csv"
    FORECASTS_FILE: Path = DATA_DIR / "forecast_log.csv"
    CEDEAR_RATIOS_FILE: Path = DATA_DIR / "cedear_ratios.csv"  # legado, ya no se usa con gsheets

    # --- Storage backend: "csv" (default, funciona sin configurar nada) o "gsheets" ---
    # El objetivo del proyecto es correr en "gsheets" para tener el log de
    # transacciones en una planilla propia -- csv es el fallback automático
    # mientras no esté configurado. ⚠️ En Streamlit Cloud el filesystem es
    # efímero: "csv" ahí NO persiste entre reinicios, usar siempre "gsheets".
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "csv").strip().lower()

    # --- Google Sheets ---
    GOOGLE_SHEETS_SPREADSHEET_ID: str = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE", str(BASE_DIR / "config" / "service_account.json")
    )

    # --- Google Drive (sincronización automática de reportes del broker) ---
    DRIVE_FOLDER_ID: str = os.getenv("DRIVE_FOLDER_ID", "")

    # --- Data providers ---
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    DEFAULT_BENCHMARK: str = os.getenv("DEFAULT_BENCHMARK", "SPY")
    HISTORY_PERIOD: str = os.getenv("HISTORY_PERIOD", "2y")
    PRICE_CACHE_TTL_SECONDS: int = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "900"))  # 15 min

    # --- CCL automático (vía CEDEAR líquido / su ADR, ver ccl_provider.py) ---
    # Se prueban en orden. Ratios de referencia -- confirmalos de tanto en
    # tanto contra BYMA o tu broker, pueden cambiar.
    CCL_PARES: tuple = (
        ("GGAL.BA", "GGAL", 10.0),   # Grupo Galicia
        ("YPFD.BA", "YPF", 1.0),     # YPF
        ("PAMP.BA", "PAM", 25.0),    # Pampa Energía
    )

    # --- Riesgo ---
    VAR_CONFIDENCE_LEVELS = (0.95, 0.99)
    STRESS_SCENARIOS = (-0.10, -0.20, -0.30, -0.34)  # shocks sobre el benchmark

    # --- Auth ---
    AUTH_CREDENTIALS_FILE: Path = BASE_DIR / "config" / "credentials.yaml"
    SESSION_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "480"))
    COOKIE_KEY: str = os.getenv("COOKIE_KEY", "tracker_riesgo_cookie_key_cambiar")

    DEBUG: bool = _get_bool("DEBUG", False)


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
