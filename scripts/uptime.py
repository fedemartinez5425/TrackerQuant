"""
Chequeo de que la app desplegada carga de verdad (lo corre
.github/workflows/uptime.yml cada 6 horas). Abre la app con un navegador
real (Playwright): si Streamlit Cloud la durmió, toca el botón para
despertarla, y espera a ver la pantalla de login. Así además cuenta como
visita y la app no se duerme por inactividad.

Sale con código 1 si la app no carga: GitHub Actions marca la corrida como
fallida y te manda un mail. Deja una captura en uptime.png.

    APP_URL=https://trackerquant.streamlit.app python scripts/uptime.py
"""
from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

TEXTO_OK = "Tracker Quant"  # título de la pantalla de login (y del sidebar)
TEXTOS_ERROR = (
    "Failed to fetch dynamically imported module",
    "trouble loading",
    "Oh no.",  # pantalla de error de Streamlit Cloud
    "Error running app",
)
BOTON_DESPERTAR = "get this app back up"
ESPERA_MAXIMA_SEGUNDOS = 300  # despertar una app dormida puede tardar un par de minutos


def _texto_de_todos_los_frames(page) -> str:
    # La app corre dentro de un iframe de *.streamlit.app.
    partes = []
    for frame in page.frames:
        try:
            partes.append(frame.inner_text("body", timeout=2000))
        except Exception:  # noqa: BLE001 - frames que se recargan mientras leemos
            pass
    return "\n".join(partes)


def main() -> int:
    url = os.environ.get("APP_URL", "").strip()
    if not url:
        print("::error::Falta el secret APP_URL (ej. https://trackerquant.streamlit.app)")
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        inicio = time.time()
        desperto = False
        resultado = 1
        while time.time() - inicio < ESPERA_MAXIMA_SEGUNDOS:
            texto = _texto_de_todos_los_frames(page)
            error = next((e for e in TEXTOS_ERROR if e in texto), None)
            if error:
                print(f"::error::La app cargó con error: «{error}»")
                break
            if TEXTO_OK in texto:
                print(f"OK: la app cargó en {time.time() - inicio:.0f} s" + (" (estaba dormida)" if desperto else ""))
                resultado = 0
                break
            boton = page.get_by_role("button", name=BOTON_DESPERTAR, exact=False)
            if not desperto and boton.count():
                print("La app estaba dormida: despertándola…")
                boton.first.click()
                desperto = True
            time.sleep(5)
        else:
            print(f"::error::La app no cargó en {ESPERA_MAXIMA_SEGUNDOS} s (spinner infinito o caída).")
        page.screenshot(path="uptime.png", full_page=True)
        browser.close()
    return resultado


if __name__ == "__main__":
    sys.exit(main())
