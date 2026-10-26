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
pip install -r requirements.txt
streamlit run app.py                 # local usa CSV en data/ salvo que haya secrets de gsheets
pytest -q tests                      # 107 tests, sin red (todo mockeado)
python -m pyflakes core pages        # pyflakes está en el venv, no en requirements.txt
```

Los tests **no deben salir a internet** (`tests/conftest.py` desactiva la descarga de Comafi).
Todo cambio de lógica en `core/` va con su test.

## Arquitectura

```
app.py                  entry point: st.navigation(), login, banner si Sheets cayó a CSV
app_helpers.py          helpers de UI + caches (st.cache_data) + invalidar_caches()
pages/                  11 páginas (Dashboard, Reporte, Cartera, Transacciones, Históricos,
                        Riesgo, Forecasting, Escenarios, Candidatos, Importar Broker, Configuración)
core/storage/           models.py (Pydantic) · base_repository.py · csv_repository.py ·
                        sheets_repository.py · __init__.py (factory get_repository())
core/portfolio/         portfolio_engine.py (tenencias, costo promedio) · historicos.py
                        (USD equivalente + alinear_dias_comunes) · attribution.py (MCTR)
core/risk/              volatility, var, correlation, stress_test, summary
core/performance/       metrics.py (CAGR, Sharpe, Sortino, drawdown, momentum, SMA, RSI; por
                        activo y para la cartera con pesos constantes)
core/decision/          candidatos.py (impacto de sumar un candidato, ranking, precio de 1
                        unidad en ARS, peso de 1 unidad)
core/forecasting/       volatility_garch (GARCH-t) · returns_forecast (cono) · backtest
core/data_providers/    yfinance + Alpha Vantage con cache en memoria · ccl_provider · comafi_ratios
core/importers/         broker_movimientos (CSV ';' formato AR) · import_service · drive_sync · portfolio_report
core/insights/          rules_engine (reglas determinísticas -> reporte Markdown)
core/auth/              streamlit-authenticator; fail-closed en Cloud
```

Pestañas de Sheets / CSV en `data/`: `instrumentos`, `transactions`, `portfolio_snapshots`,
`forecast_log`, `processed_files`, `audit_log`, `watchlist` (candidatos fuera de cartera:
ticker, tipo, ADR, ratio opcional, notas; independiente de `instrumentos`).

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
- **Caches**: históricos en memoria (`PRICE_CACHE_TTL_SECONDS`, 15 min) + `st.cache_data`;
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
Candidatos. El diseño de lo que sigue en la capa de decisión (rebalanceo, alertas, fundamentals,
export para LLM, reglas con candidatos) está en **`docs/ROADMAP.md`**.

1. **Ganancia realizada + dividendos + efectivo.** Hoy solo hay no realizada y la comisión de
   venta se pierde. Probablemente requiere tipos de movimiento nuevos (dividendo, depósito) →
   ojo con el esquema de Sheets.
2. **Ratios de Comafi persistidos en Sheets** (pestaña nueva) en vez de `data/cedear_ratios.csv`,
   que en Cloud se pierde en cada reinicio.
3. **Mapeo ticker BCBA → ADR / yfinance** cuando difieren (ej. BRKB → BRK-B).
4. **Snapshots automáticos diarios** (GitHub Actions con cron + script que use el repo de Sheets).
5. **Benchmark Merval en USD-CCL** y beta con retornos semanales para acciones argentinas.
6. **Capa de decisión**: ítems 1–5 de `docs/ROADMAP.md`.
7. Menores: `yf.download` en lote; limpiar imports sin uso (`pyflakes`); la página Riesgo
   duplica cálculos de `core/risk/summary.py`.

## Pendientes manuales de Fede

- Subir `.github/workflows/tests.yml` (CI con pytest).
- Después del deploy de `feature/candidatos`: Reboot en Streamlit Cloud y verificar que apareció
  la pestaña `watchlist` con sus 6 headers en la fila 1.
- Borrar la carpeta `.kilo/worktrees/` (copia vieja del proyecto, no está en git).
