"""
ETL diario de precios + snapshot automático. Lo corre GitHub Actions
(.github/workflows/etl-diario.yml); también se puede correr a mano:

    python scripts/etl_precios.py --dry-run      # baja y controla, no escribe nada
    python scripts/etl_precios.py                # escribe en el storage configurado

Storage: el mismo que la app (STORAGE_BACKEND=gsheets + GOOGLE_SHEETS_SPREADSHEET_ID
+ GOOGLE_SERVICE_ACCOUNT_FILE en el entorno, o CSV local por defecto).
Sale con código 1 si no pudo guardar precios: GitHub Actions marca la corrida
como fallida y te manda un mail.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import setup_logging  # noqa: E402
from config.settings import settings  # noqa: E402
from core.etl.precios import correr  # noqa: E402
from core.storage import get_backend_status, get_repository  # noqa: E402


def _anotar_en_github(resultado) -> None:
    """Avisos visibles en la corrida de Actions + resumen en la pestaña Summary."""
    if not os.getenv("GITHUB_ACTIONS"):
        return
    for p in resultado.problemas:
        nivel = "error" if p.severidad == "alto" else "warning"
        print(f"::{nivel} title=Calidad de datos ({p.tipo})::{p.ticker}: {p.detalle}")
    resumen = os.getenv("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(f"## ETL de precios\n\n{resultado.resumen()}\n\n")
            if resultado.problemas:
                f.write("| Severidad | Ticker | Tipo | Detalle |\n|---|---|---|---|\n")
                for p in resultado.problemas:
                    f.write(f"| {p.severidad} | {p.ticker} | {p.tipo} | {p.detalle} |\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="No escribe nada (ni precios, ni snapshot, ni auditoría).")
    parser.add_argument("--sin-snapshot", action="store_true", help="No guarda el snapshot automático de la cartera.")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # consola de Windows
    setup_logging()
    repo = get_repository()
    estado = get_backend_status()
    print(f"Storage: {estado['activo']} (pedido: {estado['solicitado']})")
    if settings.STORAGE_BACKEND == "gsheets" and estado["activo"] != "gsheets":
        print(f"::error::No se pudo conectar a Google Sheets: {estado['error']}")
        return 1

    resultado = correr(repo, con_snapshot=not args.sin_snapshot, escribir=not args.dry_run)
    print(resultado.resumen())
    for p in resultado.problemas:
        print(f"  {p}")
    _anotar_en_github(resultado)
    return 0 if resultado.ok else 1


if __name__ == "__main__":
    sys.exit(main())
