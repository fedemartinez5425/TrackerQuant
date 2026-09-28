"""
Sincronización automática con Google Drive: en vez de subir el CSV del
broker a mano cada vez, lo dejás en una carpeta de Drive (se puede
automatizar ESE paso con un filtro de Gmail que reenvíe el adjunto del
broker a esa carpeta -- gratis, sin código) y esta app detecta los
archivos nuevos, los tipifica mirando las COLUMNAS del CSV (no el
nombre del archivo, más robusto ante que vos lo renombres), y te deja
importarlos con un click.

Usa las mismas credenciales de service account que Google Sheets (mismo
proyecto de Google Cloud), agregando el scope de solo lectura de Drive.
No genera ningún costo: la Drive API tiene una cuota gratuita generosa
(miles de requests/día) muy por encima de lo que un uso personal necesita.
"""
from __future__ import annotations

import io
import logging

from core.storage.base_repository import BaseRepository

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _cliente_drive(credentials_info: dict | None, service_account_file: str | None):
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    scopes = SCOPES
    if credentials_info:
        creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def listar_archivos_csv(
    folder_id: str, credentials_info: dict | None = None, service_account_file: str | None = None
) -> list[dict]:
    """Lista los .csv de la carpeta de Drive indicada, más recientes primero."""
    servicio = _cliente_drive(credentials_info, service_account_file)
    query = f"'{folder_id}' in parents and trashed = false and (name contains '.csv')"
    resultado = (
        servicio.files()
        .list(q=query, fields="files(id, name, modifiedTime)", orderBy="modifiedTime desc", pageSize=50)
        .execute()
    )
    return resultado.get("files", [])


def descargar_contenido(
    file_id: str, credentials_info: dict | None = None, service_account_file: str | None = None
) -> str:
    import googleapiclient.http

    servicio = _cliente_drive(credentials_info, service_account_file)
    request = servicio.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = googleapiclient.http.MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8", errors="replace")


def detectar_tipo_archivo(contenido: str) -> str:
    """Mira la fila de encabezados (no el nombre del archivo, que puede
    cambiar) para decidir qué parser corresponde."""
    if not contenido.strip():
        return "desconocido"
    primera_linea = contenido.splitlines()[0].lower()
    if "nroticket" in primera_linea:
        return "movimientos"
    if "instrumento" in primera_linea and "total" in primera_linea and "nroticket" not in primera_linea:
        return "portfolio_report"
    return "desconocido"


def archivos_pendientes(
    folder_id: str,
    repo: BaseRepository,
    credentials_info: dict | None = None,
    service_account_file: str | None = None,
) -> list[dict]:
    """Archivos de la carpeta que todavía NO están en processed_files."""
    ya_procesados = repo.list_processed_file_ids()
    archivos = listar_archivos_csv(folder_id, credentials_info, service_account_file)
    return [a for a in archivos if a["id"] not in ya_procesados]
