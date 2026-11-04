# CLAUDE.md — Tracker Quant (Data Finance)

Contexto para Claude Code. Leelo antes de tocar código.

## Qué es

App personal en **Streamlit** para medir el riesgo de una cartera argentina (CEDEARs + acciones
argentinas directas): volatilidad, VaR/CVaR, correlación, beta, estrés, forecasting GARCH,
reporte de insights por reglas. Datos de mercado vía yfinance (Alpha Vantage de respaldo),
CCL calculado automáticamente, ratios de CEDEAR desde Comafi, importación del CSV del broker
(manual o vía Google Drive). Storage: **Google Sheets** en producción, CSV local en desarrollo.

- Idioma: código, comentarios y UI en **español rioplatense** (voseo: "cargá", "revisá").
- El usuario (Fede) prefiere respuestas **cortas y concisas**.

## Para qué sirve la app

Medir el riesgo de la cartera y **ayudar a decidir** (qué sumar, cuánto, cómo cambia el riesgo)
con números reproducibles. Lo cualitativo (noticias, gestión, balances) queda **afuera**: la app
no recomienda comprar nada, muestra el impacto cuantitativo y advierte que es un backtest.

## Deploy (importante)

- Repo: `github.com/fedemartinez5425/TrackerQuant`, rama `main`.
- **Producción = Streamlit Community Cloud**, que redeploya solo con cada push a `main`.
  No hay staging: lo que se pushea a `main` sale a producción.
- Fede commitea y pushea con **GitHub Desktop**. Trabajar en una rama y avisar qué
  archivos cambiaron; no pushear a `main` sin que lo pida.
- Configuración de producción en **Streamlit Cloud → Settings → Secrets** (no en el repo):
  `storage_backend = "gsheets"`, `google_sheets_spreadsheet_id`, `drive_folder_id`,
  `[gcp_service_account]`, `[credentials.usernames.<usuario>]`, `[cookie]`.
  Ver `.streamlit/secrets.toml.example`.
- Nunca commitear: `.streamlit/secrets.toml`, `config/credentials.yaml`,
  `config/service_account.json`, `data/*.csv`, `.env` (ya están en `.gitignore`).

## Correr y testear (Windows, PowerShell)

```powershell
.venv\Scripts\Activate.ps1          # si falla: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -r requirements-dev.txt  # = requirements.txt (versiones exactas) + pytest + pyflakes
streamlit run app.py                 # local usa CSV en data/ salvo que haya secrets de gsheets
pytest -q tests                      # 176 tests, sin red (incluye smoke test de todas las páginas)
python -m pyflakes app.py app_helpers.py app_style.py core pages scripts
python scripts/etl_precios.py --dry-run   # ETL contra Yahoo real, sin escribir nada
```

Los tests **no deben salir a internet** (`tests/conftest.py` reemplaza Yahoo/Alpha Vantage por un
proveedor sin red y desactiva la descarga de Comafi) **ni tocar `data/`** (una guarda en
`conftest.py` falla si algún test crea o modifica un CSV ahí; el smoke test redirige todos los
`settings.*_FILE` a `tmp_path`). Todo cambio de lógica en `core/` va con su test.

**Dependencias**: `requirements.txt` tiene versiones **exactas** (`==`, es lo que instala Cloud);
las directas con rangos están en `requirements.in`. Para actualizar: `pip install -U -r
requirements.in`, `pip freeze > requirements.txt` (sacar pytest/pyflakes/iniconfig/pluggy), tests
en verde y recién ahí commitear. Nunca dejar una dependencia sin fijar: un deploy instalaba
versiones nuevas solo y rompía la app (spinner infinito, componentes que no cargaban).

## Arquitectura

```
app.py                  entry point: st.navigation() por secciones (Resumen, Mi cartera, Riesgo,
                        Decidir, Ajustes), login con navegación oculta, banner si Sheets cayó a
                        CSV, configurar_almacen() y aislador de errores alrededor de pg.run()
app_helpers.py          helpers de UI + caches (st.cache_data, max_entries) + invalidar_caches() ·
                        impacto de la última operación · frescura de precios · tarjeta_alerta ·
                        avisar_despues_del_rerun (toast que sobrevive a st.rerun)
pages/                  12 páginas (Dashboard, Reporte, Cartera, Transacciones, Históricos,
                        Riesgo, Forecasting, Escenarios, Candidatos, Importar Broker, Configuración,
                        Estado del sistema)
scripts/                generar_credenciales · etl_precios (lo corre GitHub Actions) · uptime (Playwright)
.github/workflows/      tests.yml (push) · etl-diario.yml (L-V 22:30 UTC) · uptime.yml (cada 6 h).
                        Puesta en marcha y secrets: docs/GITHUB_ACTIONS.md
core/storage/           models.py (Pydantic) · base_repository.py · csv_repository.py ·
                        sheets_repository.py · __init__.py (factory get_repository())
core/portfolio/         portfolio_engine.py (tenencias, costo promedio) · historicos.py
                        (USD equivalente, tickers_de_mercado, matriz_riesgo, alinear_dias_comunes) ·
                        attribution.py (MCTR) · snapshot.py (armar_snapshot, lo usan Dashboard y ETL)
core/risk/              volatility, var, correlation, stress_test, summary
core/performance/       metrics.py (CAGR, Sharpe, Sortino, drawdown, momentum, SMA, RSI; por
                        activo y para la cartera con pesos constantes)
core/decision/          candidatos.py (impacto de sumar un candidato, ranking, precio de 1
                        unidad en ARS, peso de 1 unidad) · ultima_operacion.py (riesgo antes/
                        después de la última compra/venta + lectura en texto llano)
core/forecasting/       volatility_garch (GARCH-t) · returns_forecast (cono) · backtest
core/data_providers/    __init__ (cadena yfinance → Alpha Vantage, cache por ticker, precargar() en
                        lote, cortacircuito) · yfinance_client (timeout, yf.download) · almacen
                        (pestaña precios en memoria) · calidad (controles del ETL) · ccl_provider ·
                        comafi_ratios
core/etl/               precios.py (ETL diario: universo, extracción en lote, calidad, carga,
                        snapshot automático, auditoría)
core/sistema.py         versión deployada (lee .git) y versiones de paquetes, para Estado del sistema
core/importers/         broker_movimientos (CSV ';' formato AR) · import_service · drive_sync · portfolio_report
core/insights/          rules_engine (reglas determinísticas -> reporte Markdown)
core/viz/               palette (colores, fuente única) · charts (Plotly) · semaforos (umbrales
                        🟢🟡🔴 + pandas Styler para st.dataframe) · formato (números en formato AR)
core/auth/              streamlit-authenticator; fail-closed en Cloud
```

Pestañas de Sheets / CSV en `data/`: `instrumentos`, `transactions`, `portfolio_snapshots`,
`forecast_log`, `processed_files`, `audit_log`, `watchlist` (candidatos fuera de cartera:
ticker, tipo, ADR, ratio opcional, notas; independiente de `instrumentos`), `precios` (almacén de
cierres diarios en formato largo: fecha, ticker de yfinance, close, fuente, actualizado_en; la
reescribe entera el ETL, la app solo la lee).

Las páginas no deben tener lógica de negocio: llaman a `core/`. `core/` no importa Streamlit
(salvo `core/auth` y `core/cloud_secrets.py`).

## Invariantes y decisiones (no romper)

- **Transacciones append-only.** Nunca se editan ni se borran. Un **reverso** anula la original:
  se identifica por `notas` que empiezan con `"REVERSO de <id>"` (ver `models.REVERSO_PREFIJO`,
  `Transaction.revierte_a`, `transacciones_efectivas()`). Original y reverso se excluyen de todo
  cálculo. No se puede reversar dos veces ni reversar un reverso.
- **Tabla dimensión `instrumentos`**: tipo (`ACCION_ARG`/`CEDEAR`), `ticker_usd`, `ratio_cedear`
  viven ahí, no en cada transacción.
- **Moneda**: la cartera se valúa en ARS. Transacciones en USD se convierten con el **CCL de su
  fecha** (`tipo_cambio_ccl_historico`, `ccl_en_fecha`).
- **Riesgo en USD equivalente**: CEDEARs vía su ADR; acciones argentinas `.BA` / CCL histórico.
- **Calendarios**: nunca forward-fill de precios entre mercados. `alinear_dias_comunes()` deja solo
  días con precio de todos; excluye activos con historia corta (quedan en `df.attrs["excluidos"]`,
  la UI lo avisa con `avisar_excluidos`). `retorno_diario_cartera` re-normaliza pesos de faltantes.
- **CCL** = mediana de los pares de `settings.CCL_PARES` (GGAL 10:1, YPFD 1:1, PAMP 25:1).
- **Forecast GARCH(1,1) con dist t.** Se guarda `vol_horizonte` (raíz del promedio de varianzas del
  horizonte), no la del día N. El cono acumula varianzas diarias.
- **Datos de mercado (data engineering)**: la app NO baja la historia de Yahoo en cada visita.
  - Fuente principal = pestaña `precios`, que llena el ETL diario (`scripts/etl_precios.py`, GitHub
    Actions). Baja la ventana completa todos los días (no incremental: Yahoo ajusta el pasado por
    dividendos/splits). Guarda `HISTORY_PERIOD_BASE` (3y) por ticker y 5y para los pares del CCL.
    No pisa el almacén si trae menos del 50% de los tickers que había.
  - La app lee el almacén (`almacen.configurar(repo.list_precios)`, relectura cada 15 min) y a
    Yahoo solo le pide los días posteriores al último cierre guardado (`PERIODO_COMPLETAR`, en lote).
  - Una sola historia por ticker en memoria (`HISTORY_PERIOD_BASE`); los pedidos de 1y/2y se
    recortan. Para varios tickers usar `data_providers.precargar()` (una request), no un loop.
  - Toda llamada de red con timeout. Cortacircuito: 3 fallas seguidas → 2 min sin Yahoo; rate
    limit → 5 min. Mientras, se usa lo que haya (almacén o cache vencido). Nunca colgar la página.
  - Controles de calidad del ETL (`calidad.py`): faltante, desactualizado (> 4 ruedas), salto
    diario > 40%, hueco > 10 días, par del CCL a más de 5% de la mediana. Quedan en `audit_log`
    (`ETL_PRECIOS`), en la corrida de Actions y en Estado del sistema.
  - El snapshot diario lo guarda el ETL (uno por fecha; el botón del Dashboard queda para uno a mano).
- **Robustez**: `app.py` envuelve `pg.run()`: una excepción en una página se muestra y el resto
  sigue. Estado del sistema muestra storage, almacén, última corrida del ETL, Yahoo y versiones.
- **Caches**: históricos en memoria (`PRICE_CACHE_TTL_SECONDS`, 15 min, tope de 300 tickers) + `st.cache_data`;
  Sheets: worksheets resueltos una vez y lecturas cacheadas 60 s, invalidadas al escribir.
  Después de cualquier escritura desde una página: `invalidar_caches()`.
  Altas múltiples con `repo.add_transactions()` (una llamada a la API).
- **Cuota Google Sheets** (~60 lecturas/min): no agregar lecturas por rerun sin cache.
- **Auth fail-closed**: en Streamlit Cloud (detectado por `/mount/src/` o `HOSTNAME=streamlit`,
  o `TRACKER_ENTORNO=produccion`) la app no arranca con admin/cambiar123. Usuarios nuevos:
  `python scripts/generar_credenciales.py` (imprime el bloque para los Secrets).
- **Drive sync**: un archivo solo se marca como procesado si se importó completo
  (`ResumenImportacion.completo`).
- **Snapshots**: `valor_total_usd` está en USD (valor ARS / CCL). Los anteriores al 12/10/2026
  quedaron en ARS.
- **Esquema de Sheets/CSV**: los headers salen de las constantes `*_FIELDS` en
  `csv_repository.py`. Agregar columnas requiere migrar las pestañas existentes en Sheets.

## UI: tablas y semáforos

- Colores: `core/viz/palette.py` es la fuente única; `.streamlit/config.toml` repite la paleta
  para los widgets nativos (sliders, checkboxes, grilla de tablas).
- `st.dataframe` dibuja en canvas: el CSS no llega a las celdas. Colores y formato van por
  `semaforos.tabla(df, formatos, reglas)` (Styler) o `st.column_config`.
- Umbrales del semáforo en `core/viz/semaforos.py` (vol 25/40%, peso 15/25%, correlación
  0,4/0,7, max DD −20/−35%, prima ±3/6%, RSI 30–70). Los de vol y correlación coinciden con
  `semaforo_riesgo` y `rules_engine`: si se cambian, cambiarlos en los dos lados (hay test).
- Cada tabla con semáforo lleva debajo la leyenda (`semaforos.LEYENDA`) con los umbrales.
- **Formato argentino** en todo número visible: `$ 1.234.567,89`, `12,5 %`. Usar
  `core/viz/formato.py` (`fmt`, `moneda`, `pct`, `estilo` para Styler); `semaforos.tabla` ya lo
  aplica, Plotly lo toma de `separators` en `palette.plotly_layout_defaults` y `st.column_config`
  usa `format="localized"`. Nada de f-strings `{x:,.2f}` sueltos en la UI.
- **El dato antes que el gráfico**: el título de cada gráfico dice la conclusión ("SHOP aporta 26 %
  con 19 % del peso"); los gráficos marcan el dato clave (máximo y caída, VaR, mayor posición).
  **Rojo solo para alertas** (lo que supera un umbral), nunca decorativo.
- **Accesibilidad**: el color nunca es la única señal (ícono + texto, `tarjeta_alerta`); texto con
  contraste AA (`TEXT_MUTED` es solo para líneas); foco visible con teclado; `help=` en métricas.
- **Botones**: un primario por pantalla, verbos concretos, `st.dialog` de confirmación para lo
  irreversible (reverso). Nunca `st.success` justo antes de `st.rerun()` (no se ve): usar
  `avisar_despues_del_rerun`.

## Definiciones de métricas (`core/performance/metrics.py`)

Todo sobre precios en **USD equivalente**, retornos diarios simples `r = p_t / p_{t-1} − 1`.

- **Ventanas**: 1 y 3 años **calendario** (`VENTANAS_ANIOS`). Si la serie no cubre el 95% de la
  ventana (`COBERTURA_MINIMA`), la métrica es `None` ("—" en la UI). Años = días calendario / 365,25.
- **CAGR** = (p_final / p_inicial)^(1 / años) − 1.
- **Volatilidad anual** = desvío de r × √252.
- **Sharpe** = (CAGR − rf) / vol. `rf = settings.RISK_FREE_RATE` (4% anual por defecto).
- **Sortino** = (CAGR − rf) / (desvío de los r < 0 × √252).
- **Max drawdown** = mín(p / máximo acumulado − 1) dentro de la ventana.
- **Drawdown actual** = p_hoy / máx(últimas 252 ruedas) − 1.
- **Retorno 1m / 3m / 6m** = p_hoy / p hace 21 / 63 / 126 ruedas − 1.
- **Momentum 12-1** = p[−22] / p[−253] − 1 (de hace 12 meses a hace 1, saltea el último mes).
- **vs SMA N** = p_hoy / promedio de las últimas N ruedas − 1 (N = 50, 200).
- **RSI 14** = 100 − 100 / (1 + subas promedio / bajas promedio) en 14 cambios (simple, no Wilder).
  Sin bajas → 100; sin subas ni bajas → 50.
- **Cartera**: índice de $1 con pesos de hoy **constantes** (rebalanceo diario, vía
  `retorno_diario_cartera`); se le aplican las mismas métricas.
- **Candidatos** (`core/decision/candidatos.py`): la cartera se escala a (1 − p) y el candidato
  entra con peso p (si ya está en cartera, se suma). Se compara en los días comunes de
  tenencias + ese candidato (`dropna` por candidato, sin achicar la historia del resto).
  Δ = después − antes de vol, Sharpe y max DD a 1 y 3 años; ranking por Δ Sharpe 3a.
  Precio de 1 unidad: CEDEAR = ADR × CCL / ratio (ratio del item o Comafi); acción = `.BA`.
  Peso de 1 unidad = precio / valor de la cartera; si supera p, la UI lo alerta.
- Historia para decisión: `settings.HISTORY_PERIOD_DECISION` (3y por defecto).
- **Impacto de la última operación** (`core/decision/ultima_operacion.py`): última = transacción
  efectiva más reciente por (fecha, creado_en). Antes = cartera sin esa operación; después = la de
  hoy; las dos a precios de hoy y sobre los mismos históricos (unión de tickers, días comunes).
  Métricas: peso y aporte al riesgo (MCTR) del ticker, vol anual, VaR 95% en pesos y en %
  (como pérdida positiva), riesgo en las 2 mayores, correlación ponderada, beta. Lectura: 🔴 peso
  > 25%, 🟡 peso > 15% o aporte > 1,5 × peso, vol ± 1 pp.

## Flujo de trabajo

- **Una rama por feature** desde `main` (`/feature <nombre>`). Commits chicos, mensajes en español.
- **Plan antes de código**: archivos, cambios de esquema, tests y decisiones abiertas; esperar OK.
- **Checkpoint de esquema**: antes de tocar `*_FIELDS`, `csv_repository.py` o `sheets_repository.py`,
  frenar, avisar y seguir `/migrar-sheets` (incluye los pasos manuales para la planilla de producción).
- **Definición de terminado**: `pytest -q tests` en verde, `python -m pyflakes` limpio en los
  archivos tocados, `CLAUDE.md` (y `docs/ROADMAP.md`) actualizados. Cerrar con `/cierre`.
- **No pushear nunca** (lo hace Fede con GitHub Desktop; `git push` está bloqueado en
  `.claude/settings.json`).
- Slash commands en `.claude/commands/`: `/test`, `/feature`, `/migrar-sheets`, `/cierre`.

## Backlog (en orden de prioridad)

Hecho: G/P en USD-CCL (Cartera y Dashboard), métricas de rendimiento, watchlist + página
Candidatos, robustez (versiones fijas, timeouts, cortacircuito, Estado del sistema, smoke test),
almacén de precios + ETL diario + snapshots automáticos + uptime, UX (impacto de la última
operación, formato AR, navegación por secciones). El diseño de lo que sigue en la capa de decisión
(rebalanceo, alertas, fundamentals, export para LLM, reglas con candidatos) está en
**`docs/ROADMAP.md`**.

1. **Ganancia realizada + dividendos + efectivo.** Hoy solo hay no realizada y la comisión de
   venta se pierde. Probablemente requiere tipos de movimiento nuevos (dividendo, depósito) →
   ojo con el esquema de Sheets.
2. **Ratios de Comafi persistidos en Sheets** (pestaña nueva) en vez de `data/cedear_ratios.csv`,
   que en Cloud se pierde en cada reinicio.
3. **Mapeo ticker BCBA → ADR / yfinance** cuando difieren (ej. BRKB → BRK-B).
4. **Revisar el ratio de YPFD en `CCL_PARES`**: el control de calidad del ETL marca que el par
   YPFD.BA/YPF da un CCL ~10 veces menor que los otros dos (la mediana lo absorbe, pero hay que
   confirmar el ratio contra BYMA).
5. **Benchmark Merval en USD-CCL** y beta con retornos semanales para acciones argentinas.
6. **Capa de decisión**: ítems 1–5 de `docs/ROADMAP.md` (el 2, alertas, quedó parcial).
7. Menores: la página Riesgo duplica cálculos de `core/risk/summary.py`; el CCL histórico se pide
   a 5y en cada visita (`tipo_cambio_ccl_historico`), hoy lo cubre el almacén.

## Pendientes manuales de Fede

- Cargar los secrets de GitHub Actions (`GCP_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEETS_SPREADSHEET_ID`,
  `APP_URL`) y correr a mano *ETL diario* y *Uptime* (ver `docs/GITHUB_ACTIONS.md`).
- Después del deploy de `feature/ux` (incluye robustez y datos): Reboot en Streamlit Cloud,
  verificar la pestaña `precios` con sus 5 headers y, tras el primer ETL, Estado del sistema en verde.
- Borrar la carpeta `.kilo/worktrees/` (copia vieja del proyecto, no está en git).
