---
description: Corre pytest y pyflakes y resume los fallos
---

Corré, desde la raíz del proyecto y con el venv:

1. `.venv\Scripts\python.exe -m pytest -q tests`
2. `.venv\Scripts\python.exe -m pyflakes core pages app.py app_helpers.py tests`

Después resumí en pocas líneas:

- Cuántos tests pasaron y cuántos fallaron. Para cada fallo: test, archivo:línea y la causa probable en una frase.
- Los avisos de pyflakes **en archivos que tocamos en esta rama** (`git diff --name-only main...HEAD` + cambios sin commitear). Los del resto del repo, solo contalos.

No arregles nada todavía: proponé el arreglo y esperá el OK. Los tests nunca salen a internet; si alguno lo hace, eso es un fallo.
