# GitHub Actions: puesta en marcha

Hay tres workflows en `.github/workflows/`:

| Workflow | Cuándo corre | Qué hace | Si falla |
|---|---|---|---|
| `tests.yml` | Cada push a `main` o `feature/**` | `pip check`, pyflakes y pytest (incluye el smoke test que abre todas las páginas) | Cruz roja en el commit + mail |
| `etl-diario.yml` | Lunes a viernes 19:30 (hora argentina) y a mano | Baja precios en lote, controla calidad, reescribe la pestaña `precios`, guarda el snapshot del día | Mail de GitHub; el almacén queda con los datos de ayer |
| `uptime.yml` | Cada 6 horas y a mano | Abre la app con un navegador real, la despierta si está dormida y verifica que aparezca el login | Mail de GitHub + captura de pantalla en la corrida |

## 1. Cargar los secrets (una sola vez)

En GitHub: **repo → Settings → Secrets and variables → Actions → New repository secret**.

| Nombre | Valor |
|---|---|
| `GCP_SERVICE_ACCOUNT_JSON` | El **contenido completo** del JSON de la service account (el mismo que tenés en `config/service_account.json`, o el que descargaste de Google Cloud → IAM → Service accounts → Keys). Pegalo tal cual, con las llaves `{ }`. |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | El mismo valor de `google_sheets_spreadsheet_id` de los Secrets de Streamlit Cloud (lo que va entre `/d/` y `/edit` en la URL de la planilla). |
| `APP_URL` | `https://trackerquant.streamlit.app` |

Si solo tenés la service account en formato TOML (Secrets de Streamlit), armá el JSON con los mismos campos:
`type`, `project_id`, `private_key_id`, `private_key`, `client_email`, `client_id`, `auth_uri`, `token_uri`,
`auth_provider_x509_cert_url`, `client_x509_cert_url`.

## 2. Primera corrida del ETL (a mano)

1. Pusheá `main` con los workflows.
2. **Actions → ETL diario → Run workflow**.
3. Al terminar (1–2 min), abrí la corrida: en **Summary** está el resumen y la tabla de problemas de calidad.
4. En la planilla tiene que aparecer la pestaña `precios` con miles de filas.
5. En la app: **Estado del sistema → Almacén de precios** tiene que estar en verde.

## 3. Uptime

**Actions → Uptime → Run workflow**. Si falla, en la corrida hay un artefacto `uptime` con la captura de lo
que vio el navegador.

## 4. Notificaciones

GitHub manda mail cuando falla un workflow programado a quien lo creó o lo editó por última vez. Revisá
en **github.com → Settings → Notifications → Actions** que esté tildado "Send notifications for failed
workflows only".

## 5. Ojo: GitHub pausa los cron por inactividad

En un repo sin commits por **60 días**, GitHub desactiva los workflows programados (te avisa por mail).
Para reactivarlos: **Actions → (workflow) → Enable workflow**, o hacé cualquier commit.

## Correr el ETL en tu máquina

```powershell
python scripts/etl_precios.py --dry-run   # baja y controla, no escribe nada
python scripts/etl_precios.py             # escribe en el storage configurado (.env / secrets)
```
