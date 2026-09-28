"""
Ratios de CEDEAR desde el listado oficial de Comafi (Custodia Global),
en vez de hardcodearlos en settings.py.

Comafi publica un xlsx descargable con todos los programas de CEDEAR.
Como el formato de esa planilla no lo controlamos nosotros (puede cambiar
de columnas, formato de texto del ratio, etc.), el parser es defensivo:
si no encuentra lo que espera, devuelve una lista vacía en vez de romper,
y siempre se puede revisar la tabla parseada antes de confiar en ella
(botón "Actualizar desde Comafi" en ⚙️ Configuración).

El resultado se cachea en data/cedear_ratios.csv para no tener que bajar
el xlsx en cada uso, y para que la app siga funcionando aunque Comafi
esté caído (usa el último CSV bueno que haya).
"""
from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

COMAFI_XLSX_URL = "https://www.comafi.com.ar/custodiaglobal/Multimedios/otros/14779.xlsx"

# Nombres de columnas esperables (Comafi puede variar mayúsculas/espacios/tildes).
_COL_TICKER_CANDIDATOS = ["identificacion", "mercado", "ticker", "simbolo", "especie"]
_COL_RATIO_CANDIDATOS = ["ratio"]
_COL_PAIS_CANDIDATOS = ["pais", "origen"]
_COL_NOMBRE_CANDIDATOS = ["denominacion", "programa"]


def _normalizar(texto: str) -> str:
    import unicodedata

    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return texto.lower().strip()


def _encontrar_columna(columnas: list[str], candidatos: list[str]) -> str | None:
    normalizadas = {c: _normalizar(c) for c in columnas}
    for col, norm in normalizadas.items():
        if any(cand in norm for cand in candidatos):
            return col
    return None


def _parsear_ratio(valor) -> float | None:
    """El ratio en Comafi puede venir como número (9), como texto "9 a 1",
    "9:1", "9 x 1", etc. Extrae la cantidad de CEDEARs por 1 acción/ADR."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if valor > 0 else None

    texto = str(valor).strip()
    if not texto:
        return None

    # Patrones tipo "9 a 1", "9:1", "9x1", "9 x 1"
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:a|:|x|-)\s*(\d+(?:[.,]\d+)?)", texto, re.IGNORECASE)
    if match:
        num = float(match.group(1).replace(",", "."))
        den = float(match.group(2).replace(",", "."))
        return num / den if den else None

    # Un solo número suelto en el texto
    match = re.search(r"(\d+(?:[.,]\d+)?)", texto)
    if match:
        return float(match.group(1).replace(",", "."))

    return None


def parsear_workbook(contenido_bytes: bytes) -> pd.DataFrame:
    """Parsea el contenido binario de un xlsx de Comafi. Separado de la
    descarga HTTP para poder testear el parseo con archivos sintéticos."""
    xls = pd.ExcelFile(BytesIO(contenido_bytes))
    filas_totales = []

    for hoja in xls.sheet_names:
        try:
            df_crudo = xls.parse(hoja, header=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo leer la hoja '%s' del xlsx de Comafi: %s", hoja, exc)
            continue

        # Busca la fila de encabezados (contiene "ratio" en alguna celda)
        fila_header = None
        for i in range(min(10, len(df_crudo))):
            fila_texto = " ".join(_normalizar(v) for v in df_crudo.iloc[i].tolist() if v is not None)
            if "ratio" in fila_texto:
                fila_header = i
                break
        if fila_header is None:
            continue

        columnas = [str(c) for c in df_crudo.iloc[fila_header].tolist()]
        datos = df_crudo.iloc[fila_header + 1 :].copy()
        datos.columns = columnas

        col_ticker = _encontrar_columna(columnas, _COL_TICKER_CANDIDATOS)
        col_ratio = _encontrar_columna(columnas, _COL_RATIO_CANDIDATOS)
        col_pais = _encontrar_columna(columnas, _COL_PAIS_CANDIDATOS)
        col_nombre = _encontrar_columna(columnas, _COL_NOMBRE_CANDIDATOS)

        if not col_ticker or not col_ratio:
            logger.warning("Hoja '%s' de Comafi: no se encontraron columnas de ticker/ratio esperadas.", hoja)
            continue

        for _, fila in datos.iterrows():
            ticker = fila.get(col_ticker)
            if ticker is None or str(ticker).strip() == "" or str(ticker).lower() == "nan":
                continue
            ratio = _parsear_ratio(fila.get(col_ratio))
            filas_totales.append(
                {
                    "ticker": str(ticker).upper().strip(),
                    "ratio": ratio,
                    "pais": str(fila.get(col_pais, "")).strip() if col_pais else "",
                    "nombre": str(fila.get(col_nombre, "")).strip() if col_nombre else "",
                    "hoja_origen": hoja,
                }
            )

    return pd.DataFrame(filas_totales)


def descargar_y_parsear(url: str = COMAFI_XLSX_URL) -> pd.DataFrame:
    """Descarga el xlsx de Comafi y devuelve un DataFrame con columnas
    normalizadas: ticker, ratio, pais, nombre. Puede devolver un DataFrame
    vacío si algo en el parseo no coincide con lo esperado -- nunca levanta
    una excepción hacia arriba salvo error de red."""
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return parsear_workbook(resp.content)


def actualizar_cache(cache_file: Path, url: str = COMAFI_XLSX_URL) -> tuple[pd.DataFrame, str | None]:
    """Descarga, parsea y guarda en cache_file. Devuelve (df, error).
    Si hay error, df puede venir vacío o ser el último cache válido."""
    try:
        df = descargar_y_parsear(url)
        if df.empty:
            return _leer_cache(cache_file), "El parseo no encontró filas válidas (formato de Comafi cambió?)."
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_file, index=False)
        logger.info("Ratios de CEDEAR actualizados desde Comafi: %d filas.", len(df))
        return df, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo actualizar ratios desde Comafi: %s", exc)
        return _leer_cache(cache_file), f"No se pudo conectar a Comafi ({exc}). Usando el último cache guardado."


def _leer_cache(cache_file: Path) -> pd.DataFrame:
    if cache_file.exists():
        return pd.read_csv(cache_file)
    return pd.DataFrame(columns=["ticker", "ratio", "pais", "nombre", "hoja_origen"])


def leer_cache(cache_file: Path) -> pd.DataFrame:
    """Versión pública de _leer_cache, para usar desde la UI."""
    return _leer_cache(cache_file)


def obtener_ratio(ticker: str, cache_file: Path) -> float | None:
    df = _leer_cache(cache_file)
    if df.empty:
        return None
    fila = df[df["ticker"] == ticker.upper().strip()]
    if fila.empty:
        return None
    valor = fila.iloc[0]["ratio"]
    return float(valor) if pd.notna(valor) else None
