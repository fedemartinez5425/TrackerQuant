---
description: Cierra la tarea - actualiza CLAUDE.md y ROADMAP.md y lista qué commitear
---

Cerrá la tarea actual:

1. Corré `/test`. Si algo falla, frená y avisame.
2. Actualizá `CLAUDE.md`:
   - Arquitectura: módulos, páginas o pestañas nuevas.
   - Definiciones de métricas: si se agregó o cambió alguna fórmula.
   - Invariantes y decisiones nuevas.
   - Backlog: marcá lo hecho y sacalo de la lista de pendientes.
   - Cantidad de tests en "Correr y testear".
3. Actualizá `docs/ROADMAP.md`: marcá lo implementado y anotá lo que quedó pendiente o cambió de diseño.
4. Commiteá esos cambios con un mensaje en español. **No pushees.**
5. Dame un resumen corto:
   - qué se hizo,
   - commits de la rama (`git log --oneline main..HEAD`),
   - archivos cambiados (`git diff --stat main...HEAD`) y archivos sin commitear que **no** son de esta tarea,
   - pasos manuales pendientes (migración de Sheets, Reboot en Streamlit Cloud, push y merge desde GitHub Desktop).
