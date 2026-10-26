---
description: Checklist para agregar una pestaña o columna al esquema de Sheets/CSV
argument-hint: <pestaña o columna>
---

Cambio de esquema: **$ARGUMENTS**. Producción usa Google Sheets y no hay staging: un esquema mal migrado rompe la app al deployar. Seguí este checklist y marcá cada punto.

**Código**

- [ ] Constante `*_FIELDS` en `core/storage/csv_repository.py` (fuente única de headers). Columnas nuevas **al final**, nunca en el medio.
- [ ] Modelo Pydantic en `core/storage/models.py` con `to_row()` / `from_row()`. `from_row` tolera la columna vacía o ausente (filas viejas).
- [ ] `BaseRepository`: método abstracto nuevo (si es una pestaña).
- [ ] `CsvRepository`: archivo en `config/settings.py`, `_ensure_file`, parámetro opcional en el constructor (no romper los tests que lo construyen) y `core/storage/__init__.py`.
- [ ] `SheetsRepository`: constante `SHEET_*` y la tupla `(titulo, headers)` del `__init__` (crea la pestaña si falta). Lecturas por `_dicts` (cache de 60 s); escrituras invalidan con `_invalidar`. Sin lecturas nuevas por rerun (cuota ~60/min).
- [ ] Tests: CSV en `tmp_path` y Sheets con worksheet mockeado (`tests/test_sheets_repository.py`). Sin red.
- [ ] `/test` en verde.

**Pasos manuales en la planilla de producción** (dejáselos escritos a Fede en el resumen)

- **Pestaña nueva**: `SheetsRepository` la crea sola con sus headers al primer arranque después del deploy (hace falta un **Reboot** de la app en Streamlit Cloud). Verificar que apareció y que la fila 1 coincide con `*_FIELDS`.
- **Columna nueva en pestaña existente**: NO se agrega sola. Antes del deploy, escribir el header exacto en la primera columna libre de la fila 1 de esa pestaña. Las filas viejas quedan vacías en esa columna (por eso `from_row` tiene que tolerarlo).
- **Renombrar o borrar columnas**: evitarlo. Si no hay otra, plan de migración aparte y backup de la planilla (Archivo → Hacer una copia) antes.
- Después del deploy: Reboot y probar una lectura y una escritura desde la app.

Actualizá `CLAUDE.md` (sección Arquitectura / esquema) con la pestaña o columna nueva.
