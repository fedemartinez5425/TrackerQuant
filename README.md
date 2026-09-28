# ⚠️ Tracker Quant — Data Finance

Panel de riesgo de cartera personal: mide volatilidad, VaR/CVaR, correlación,
escenarios de estrés y forecasting de volatilidad (GARCH), con **todos los
datos automatizados** (yfinance, CCL automático, ratios de CEDEAR desde
Comafi, importación desde el broker con sincronización automática vía
Google Drive) y el log de transacciones en **Google Sheets**, diseñado
como una base de datos relacional. Diseño tipo dashboard de BI profesional
(paleta grafito + verde menta, gráficos con degradados y etiquetas de dato).

## Instalación local

```bash
cd tracker_riesgo
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Abre en `http://localhost:8501`. Login por defecto: usuario `admin`,
contraseña `cambiar123` (se genera solo la primera vez). Cambiala con:

```bash
python scripts/generar_credenciales.py
```

## Módulos (10 páginas, navegación centralizada en `app.py`)

| Página | Qué hace |
|---|---|
| 📊 Dashboard | KPIs, semáforo, donut de exposición, evolución, histograma, contribución al riesgo, top señales |
| 📄 Reporte | Diagnóstico + recomendaciones en Markdown (reglas cuantitativas, no IA) — para llevar a investigar |
| 💼 Cartera | Posiciones actuales — precio BCBA + teórico vía CCL, en pesos |
| 📝 Transacciones | Alta de movimientos + tabla dimensión de Instrumentos (tipo/ratio, se define una vez) |
| 📈 Históricos | Precios históricos (USD equivalente) usados en los cálculos |
| ⚠️ Riesgo | Volatilidad/VaR/CVaR + Correlación + Estrés, en tabs |
| 🔮 Forecasting | Volatilidad con GARCH(1,1), cono de incertidumbre de retornos, backtest de precisión |
| 🕰️ Escenarios | Riesgo Histórico (reconstrucción a fecha pasada) + Simulador (qué pasaría si) |
| 📥 Importar Broker | Carga masiva desde CSV del broker + reconciliación |
| ⚙️ Configuración | Storage, ratios de Comafi, CCL, **sincronización con Drive**, usuarios, auditoría |

## Diseño de datos: relacional, no plano

- **`instrumentos`** (dimensión): un ticker, definido UNA vez (tipo, ADR,
  ratio). Si un ratio cambia (split, ampliación de capital), se corrige
  en un solo lugar y aplica a toda la cartera retroactivamente.
- **`transactions`** (hechos, append-only): solo referencia el ticker —
  no repite tipo/ratio en cada fila.
- **`portfolio_snapshots`** (hechos): fotos manuales de valor+riesgo, para
  graficar evolución real con el tiempo.
- **`forecast_log`** (hechos): cada forecast de volatilidad emitido, para
  poder medir después qué tan preciso fue (la volatilidad *realizada*
  nunca se guarda — se recalcula on-the-fly desde el histórico de precios,
  así el sistema queda siempre exacto y 100% append-only).
- **`processed_files`**: qué archivos de Drive ya se importaron (idempotencia).
- **`audit_log`**: quién hizo qué y cuándo.

## Importante: moneda de los valores

El valor de la cartera, costos, precios y G/P se muestran en **pesos
argentinos ($)**. Los cálculos de **riesgo** se hacen sobre una serie de
precios convertida a **USD equivalente** internamente (necesario para que
CEDEARs y acciones argentinas directas sean comparables matemáticamente),
pero el resultado en pesos que ves en la app siempre está en $ ARS.

## Deploy: GitHub + Streamlit Community Cloud + Google Cloud (gratis)

Todo el stack corre en capas gratuitas: GitHub (repo privado o público),
Streamlit Community Cloud (hosting gratuito), Google Sheets API + Google
Drive API (cuota gratuita muy por encima de lo que un uso personal necesita).
No hay ningún componente pago en este diseño.

### 1. Google Cloud: Sheets API + Drive API

1. Andá a [Google Cloud Console](https://console.cloud.google.com/), creá
   un proyecto (o reusá uno).
2. Habilitá **Google Sheets API** y **Google Drive API** (APIs y servicios
   → Habilitar APIs).
3. Creá una **cuenta de servicio** (IAM y administración → Cuentas de
   servicio → Crear). Generale una clave JSON (Claves → Agregar clave → JSON)
   y guardala.
4. Creá una planilla de Google Sheets nueva y compartila (botón Compartir)
   con el email de la cuenta de servicio (`...@...iam.gserviceaccount.com`),
   como **Editor**. Copiá el ID de la planilla (en la URL, entre `/d/` y `/edit`).
5. (Para la sincronización automática) Creá una carpeta en Google Drive,
   compartila con el mismo email de la cuenta de servicio (alcanza con
   **Lector**), y copiá el ID de la carpeta (en la URL, después de `/folders/`).

### 2. GitHub

```bash
git init
git add .
git commit -m "Tracker Quant - Data Finance"
git branch -M main
git remote add origin https://github.com/tu-usuario/tracker-riesgo.git
git push -u origin main
```

El `.gitignore` ya excluye `.env`, `config/credentials.yaml`,
`config/service_account.json` y `.streamlit/secrets.toml` — nunca se suben
credenciales al repo.

### 3. Streamlit Community Cloud

1. Entrá a [share.streamlit.io](https://share.streamlit.io), conectá tu
   cuenta de GitHub y elegí el repo.
2. Main file: `app.py`.
3. Antes de deployar (o después, desde "Settings → Secrets"), pegá el
   contenido de `.streamlit/secrets.toml.example` con tus valores reales
   (ver esa plantilla para el formato exacto de cada campo, incluyendo el
   JSON de la cuenta de servicio como tabla TOML).
4. Deploy. Listo — la app corre 100% en la nube, sin servidor propio.

Como el filesystem de Streamlit Cloud es efímero, en producción `storage_backend`
**tiene que ser `"gsheets"`** (se configura en los Secrets, no en `.env`).

## Importar movimientos desde tu broker

**Manual** (📥 Importar Broker): subís el CSV de movimientos, se detecta
automáticamente CEDEAR vs. acción argentina directa, se registra el
instrumento la primera vez, y nunca se duplica (usa el número de ticket
del broker). También podés reconciliar contra el portfolio report del broker.

**Automática** (⚙️ Configuración → Sincronización con Drive): dejás el CSV
en una carpeta de Drive (podés automatizar ese paso con un filtro de Gmail
que reenvíe el adjunto del broker a esa carpeta, gratis y sin código) y la
app detecta los archivos nuevos, los tipifica mirando las columnas del CSV
(no el nombre del archivo), y los importás con un click.

## Cómo se calcula el CCL automáticamente

```
CCL = (precio_CEDEAR_ARS × ratio) / precio_ADR_USD
```

Por defecto: `GGAL.BA/GGAL` (10:1), `YPFD.BA/YPF` (1:1), `PAMP.BA/PAM`
(25:1). También se calcula una **serie histórica de CCL** para convertir
acciones argentinas directas a USD equivalente en toda la ventana de
riesgo, no solo con el valor de hoy.

## Forecasting de volatilidad (GARCH)

Se usa GARCH(1,1) (librería `arch`, estándar de la industria) porque
modela el "clustering" de volatilidad — algo que un promedio móvil no
captura. Ajustar el modelo tarda milisegundos incluso con años de
historia diaria, así que no hace falta ninguna capa extra de caché: el
cuello de botella real es traer el histórico de precios, que ya está
cacheado. Lo único que se persiste en la base de datos es el **forecast
emitido** (fecha, horizonte, volatilidad pronosticada, pesos vigentes);
la volatilidad *realizada* se recalcula siempre on-the-fly para el
backtest, nunca se guarda, así el sistema no puede desincronizarse de la
realidad.

El cono de retornos usa la misma volatilidad pronosticada para estimar un
RANGO probable de resultados (no una dirección) — se explicita en la UI
que esto no es una predicción de si la cartera va a subir o bajar.

## Reporte de riesgo (Markdown, para investigar con IA)

📄 Reporte genera un diagnóstico con reglas cuantitativas determinísticas
(no IA, no caja negra) a partir de tus métricas de riesgo: si la
volatilidad es alta, sugiere priorizar empresas maduras y sectores
defensivos; si el beta es alto, sugiere buscar beta bajo; si la
correlación es alta, sugiere diversificar; y señala qué posiciones
concentran más riesgo del que su tamaño sugiere. Pensado como punto de
partida para copiar y pegar en una IA externa y seguir investigando — el
reporte mismo aclara que no es asesoramiento financiero personalizado.

## Identidad visual

Paleta grafito + verde menta, tipografía Space Grotesk / Inter / JetBrains
Mono, definida en `app_style.py` (CSS) y `core/viz/palette.py` (colores
también usados por los gráficos de Plotly). Los gráficos se arman con
funciones reutilizables en `core/viz/charts.py`.

## Estructura del proyecto

```
tracker_riesgo/
├── app.py                    # entry point — st.navigation(), header de marca, auth gate
├── app_helpers.py            # helpers de UI compartidos
├── app_style.py              # CSS global
├── pages/
│   ├── 1_Dashboard.py
│   ├── 9_Reporte.py
│   ├── 2_Cartera.py
│   ├── 3_Transacciones.py
│   ├── 4_Historicos.py
│   ├── 5_Riesgo.py            # tabs: VaR/CVaR, Correlación, Estrés
│   ├── 10_Forecasting.py      # tabs: Volatilidad GARCH, Cono de Retornos, Backtest
│   ├── 6_Escenarios.py        # tabs: Riesgo Histórico, Simulador
│   ├── 7_Importar_Broker.py
│   └── 8_Configuracion.py     # incluye Sincronización con Drive
├── core/
│   ├── auth/                   # st.secrets o credentials.yaml local
│   ├── cloud_secrets.py         # puente hacia st.secrets
│   ├── data_providers/          # yfinance + Alpha Vantage + CCL automático + ratios Comafi
│   ├── importers/                # parsers del broker + servicio de importación + Drive sync
│   ├── forecasting/               # GARCH, cono de retornos, backtest
│   ├── insights/                   # motor de reglas -> reporte Markdown
│   ├── portfolio/                   # cartera, pesos, contribución al riesgo, históricos USD-eq.
│   ├── risk/                         # volatilidad, VaR, CVaR, correlación, estrés, resumen
│   ├── viz/                           # paleta de colores + constructores de gráficos Plotly
│   ├── storage/                        # modelos Pydantic + repositorio (CSV / Google Sheets)
│   └── validation/
├── config/                              # settings.py, logging, credentials.yaml (se genera solo)
├── scripts/generar_credenciales.py
├── data/                                 # CSVs locales (si STORAGE_BACKEND=csv)
└── tests/
```

## Testing

```bash
pytest tests/
```

59+ tests cubren el motor de cartera, riesgo, importación de broker,
reglas de insights y forecasting — sin necesidad de red ni de Streamlit
corriendo (todo mockeado con datos sintéticos).
