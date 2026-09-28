"""
Factory de repositorio. El resto de la app llama a get_repository()
y nunca importa CsvRepository/SheetsRepository directamente.

Resuelve credenciales en este orden: st.secrets (Streamlit Cloud) primero,
luego .env / archivos locales (desarrollo). Así el mismo código corre
local y en la nube sin cambiar una línea.
"""
from __future__ import annotations

import logging
from pathlib import Path

from config.settings import settings
from core.cloud_secrets import get_secret
from core.storage.base_repository import BaseRepository
from core.storage.csv_repository import CsvRepository

logger = logging.getLogger(__name__)

_repository: BaseRepository | None = None


def get_repository() -> BaseRepository:
    global _repository
    if _repository is not None:
        return _repository

    # El backend se lee de st.secrets primero (Streamlit Cloud), luego de .env
    backend = str(get_secret(["storage_backend"], settings.STORAGE_BACKEND)).strip().lower()
    if backend == "gsheets":
        try:
            spreadsheet_id = get_secret(["google_sheets_spreadsheet_id"], settings.GOOGLE_SHEETS_SPREADSHEET_ID)
            if not spreadsheet_id:
                raise RuntimeError("Falta GOOGLE_SHEETS_SPREADSHEET_ID (.env o st.secrets)")

            # st.secrets["gcp_service_account"] (TOML) o archivo JSON local
            credentials_info = get_secret(["gcp_service_account"])
            credentials_info = dict(credentials_info) if credentials_info else None
            service_account_file = None
            if not credentials_info:
                if not Path(settings.GOOGLE_SERVICE_ACCOUNT_FILE).exists():
                    raise RuntimeError(
                        f"Sin credenciales: no hay st.secrets['gcp_service_account'] ni archivo en "
                        f"{settings.GOOGLE_SERVICE_ACCOUNT_FILE}"
                    )
                service_account_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE

            from core.storage.sheets_repository import SheetsRepository

            _repository = SheetsRepository(
                spreadsheet_id=spreadsheet_id,
                credentials_info=credentials_info,
                service_account_file=service_account_file,
            )
            logger.info("Storage backend: Google Sheets")
            return _repository
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "No se pudo inicializar Google Sheets (%s). Usando CSV local como fallback.", exc
            )

    _repository = CsvRepository(
        transactions_file=settings.TRANSACTIONS_FILE,
        audit_file=settings.AUDIT_LOG_FILE,
        snapshots_file=settings.SNAPSHOTS_FILE,
        instrumentos_file=settings.INSTRUMENTOS_FILE,
        processed_files_file=settings.PROCESSED_FILES_FILE,
        forecasts_file=settings.FORECASTS_FILE,
    )
    logger.info("Storage backend: CSV local (%s)", settings.DATA_DIR)
    return _repository


def reset_repository_cache() -> None:
    """Útil para tests o para cuando el usuario cambia de backend en Configuración."""
    global _repository
    _repository = None