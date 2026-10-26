---
description: Arranca una feature nueva en su rama, con plan y checkpoints
argument-hint: <nombre-de-la-feature>
---

Feature nueva: **$ARGUMENTS**

1. Leé `CLAUDE.md` (invariantes, definiciones de métricas, flujo de trabajo) y `docs/ROADMAP.md` si la feature está ahí.
2. Creá la rama `feature/$ARGUMENTS` desde `main` (`git checkout -b feature/$ARGUMENTS main`). Si hay cambios sin commitear en `main`, avisame antes.
3. **Antes de escribir código**, mostrame un plan corto:
   - archivos nuevos y modificados,
   - cambios de esquema (pestañas o columnas de Sheets/CSV),
   - tests que vas a agregar,
   - decisiones de diseño que tenga que tomar yo.
   Esperá mi OK.

Recordatorios mientras trabajás:

- **Checkpoint de esquema**: antes de tocar `*_FIELDS`, `csv_repository.py` o `sheets_repository.py`, frená, avisame y seguí `/migrar-sheets`.
- `core/` no importa Streamlit; las páginas solo llaman a `core/`. Todo cambio de lógica en `core/` va con test, sin red (series sintéticas y mocks).
- Commits chicos, con mensajes en español. **No pushees** (lo hago yo con GitHub Desktop).

**Definición de terminado**: `pytest -q tests` en verde, `python -m pyflakes` limpio en los archivos tocados, `CLAUDE.md` (y `docs/ROADMAP.md` si aplica) actualizados. Cerrá con `/cierre`.
