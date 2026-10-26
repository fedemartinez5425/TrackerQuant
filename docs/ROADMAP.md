# Roadmap — Tracker Quant

Diseño de lo que viene después de la capa de decisión (métricas + candidatos).
Nada de esto está implementado todavía. Cada ítem se arranca con `/feature <nombre>`
y respeta las invariantes de `CLAUDE.md`.

Estado: ✅ hecho · 🟡 en curso · ⬜ pendiente

| # | Ítem | Estado |
|---|------|--------|
| — | G/P en USD-CCL (Cartera y Dashboard) | ✅ |
| — | Métricas de rendimiento (`core/performance/metrics.py`) | ✅ |
| — | Watchlist + página Candidatos (`core/decision/candidatos.py`) | 🟡 |
| 1 | Simulador de rebalanceo | ⬜ |
| 2 | Alertas en el Dashboard | ⬜ |
| 3 | Snapshot de fundamentals | ⬜ |
| 4 | Export del Reporte para LLM | ⬜ |
| 5 | `rules_engine` con candidatos concretos | ⬜ |

---

## 1. Simulador de rebalanceo

**Objetivo:** pasar de "qué conviene" a "qué compro y vendo, en unidades, y cómo queda".

**Entrada**
- Cartera actual (`construir_cartera`) y pesos objetivo por ticker (tenencias + candidatos
  de la watchlist). Los pesos objetivo los arma el usuario o salen del ranking.
- Aporte mensual opcional (ARS) y cantidad de meses a simular.
- Comisión configurable: `settings.COMISION_TOTAL = 0.006` (0,6% todo incluido: comisión +
  derechos de mercado + IVA), aplicada sobre el monto de cada operación.
- Permitir ventas: sí/no (si no, solo se rebalancea con aportes).

**Precio automático**
- Precio por unidad en ARS con `candidatos.precio_unidad_ars` (CEDEAR: ADR × CCL / ratio;
  acción: BCBA). Para tenencias, el `precio_final` de `Position`.

**Algoritmo (`core/decision/rebalanceo.py`)**
1. Valor objetivo por ticker = (valor cartera + aporte) × peso objetivo.
2. Diferencia en ARS → unidades **enteras** (`floor` para compras, `ceil` hacia el objetivo
   en ventas, sin quedar en negativo).
3. Greedy para el efectivo sobrante: comprar 1 unidad más del ticker más por debajo de su
   objetivo mientras alcance la plata (incluida la comisión).
4. Aportes mensuales: repetir 1–3 por mes con precios constantes (no proyecta precios).
5. Resultado: `PlanRebalanceo` (dataclass) con filas `{ticker, accion, unidades, precio,
   monto, comision}`, efectivo sobrante y pesos antes/después.

**Antes/después**
- Riesgo: `calcular_resumen_riesgo` con los pesos nuevos (vol, VaR, CVaR, beta).
- Rendimiento: `metricas_cartera` con pesos antes/después (CAGR, Sharpe, max DD a 1 y 3 años).
- Misma advertencia de backtest que en Candidatos.

**No hace:** cargar transacciones. El plan es una propuesta; las operaciones se cargan a
mano o vía importación del broker (las transacciones siguen siendo append-only).

**Tests:** unidades enteras, comisión, efectivo sobrante nunca negativo, no vender más de
lo que hay, aportes acumulados.

---

## 2. Alertas en el Dashboard

Una sección "Alertas" compacta arriba del Dashboard, con tres tipos. Lógica en
`core/insights/alertas.py` (funciones puras sobre DataFrames); datos con cache.

- **Próximos balances**: `yfinance.Ticker(ticker_usd).get_earnings_dates()` para tenencias
  y watchlist (CEDEARs vía ADR; acciones argentinas vía `.BA` si yfinance lo trae).
  Cache de 24 h (`st.cache_data(ttl=86400)` en `app_helpers` + cache en memoria en el
  data provider). Alerta si hay balance en los próximos 14 días.
- **Movimiento > 2σ**: retorno del último día vs. desvío diario de las últimas 63 ruedas
  (USD equivalente). Alerta si `|r_hoy| > 2 × σ_63`. Aplica a tenencias y watchlist.
- **Cruce de SMA200**: el precio cruzó la SMA200 en las últimas 5 ruedas (signo de
  `precio − SMA200` cambió). Reusa `metrics.vs_sma`.

Cuota: earnings y precios salen de yfinance (no de Sheets), así que no suman lecturas a
la planilla. Sin red en tests: series sintéticas y un DataFrame de earnings mockeado.

---

## 3. Snapshot de fundamentals

`core/data_providers/fundamentals.py`: lee `yfinance.Ticker(t).info` (ya existe
`data_providers.get_info`) y normaliza a un dict chico:

| Campo | Clave de `info` |
|-------|-----------------|
| P/E forward | `forwardPE` |
| Crecimiento de ingresos (YoY) | `revenueGrowth` |
| Margen bruto / operativo / neto | `grossMargins` / `operatingMargins` / `profitMargins` |
| Flujo de caja libre | `freeCashflow` (y FCF yield = FCF / `marketCap`) |

- Faltantes → `None` (muchos ADRs argentinos no traen todo).
- Cache de 24 h. Se muestra como tabla en Candidatos (tenencias + watchlist).
- Es un snapshot: no se guarda histórico (si hiciera falta, pestaña nueva → `/migrar-sheets`).

---

## 4. Export del Reporte para LLM

La página Reporte ya genera Markdown (`generar_reporte_markdown`). Sumarle secciones:

- **Ranking de candidatos**: la tabla de `rankear_candidatos` (deltas a 1 y 3 años,
  correlación, posición más correlacionada, peso de 1 unidad) con el peso objetivo usado.
- **Plan de rebalanceo** (cuando exista #1): operaciones en unidades y antes/después.
- **Métricas por activo** de tenencias y watchlist, y fundamentals (#3).
- Un encabezado de contexto: fecha, CCL, valor de la cartera, supuestos (rf, ventanas,
  comisión) y la advertencia de backtest.
- Botón "Copiar para LLM" (`st.code` + `st.download_button` con el `.md`).

Objetivo: pegar un solo bloque en un LLM con todo el contexto cuantitativo, y dejar lo
cualitativo (noticias, gestión) para esa conversación.

---

## 5. `rules_engine` con candidatos concretos

Hoy las recomendaciones son genéricas ("diversificá", "bajá la concentración"). Pasar el
ranking a `generar_insights(..., ranking=None)` y, cuando haya:

- Concentración alta → nombrar los 1–2 candidatos con mayor `delta_vol_3a` negativo y su
  correlación con la posición dominante.
- Correlación alta entre tenencias → candidato con menor `corr_cartera`.
- Sharpe bajo → candidato con mayor `delta_sharpe_3a`, avisando si 1 unidad supera el
  peso objetivo.
- Siempre con la advertencia de backtest y sin "comprá X": el formato es "X mejoraría Y
  en el período analizado".

Reglas determinísticas, testeadas con un ranking armado a mano.
