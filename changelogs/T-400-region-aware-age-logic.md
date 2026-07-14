# T-400 — Region-Aware Age Logic: consent_age_threshold + country resolution

| Field | Value |
|---|---|
| **Type** | Feature / Compliance |
| **Priority** | High — COPPA (US) + Digital ECA/LGPD (BR) compliance |
| **Status** | ✅ Done — ST-01 ✅ ST-02 ✅ ST-03 ✅ tests 3-5 PASS 18/18 (2026-07-14); tests 1-2 movidos a T-607 (subitem creado) |
| **Date** | 2026-07-12 |
| **Workstream** | Compliance / Auth |
| **Depends-on** | EXT-001 ✅ (Play Developer API), INFRA-001 ✅ (GCS), T-252 ⬜ (Play Billing plugin — Signal 1) |
| **Desbloquea** | T-406 (IARC rating — store-level complement) |
| **Architecture ref** | `rnd_research/2026-06-04_motamaze-architecture-final.md` lines 1104–1121, 1199; CM-05 line 1987 |

---

## Descripción

Implementa la resolución de país por usuario (3 señales) y almacena en `users/{uid}.consent` el país resuelto + el threshold de edad aplicable. Alimenta a `consent_age_threshold(country)` ya definida en la arquitectura.

**Por qué existe:** COPPA (US) protege a menores de 13; Brasil Digital ECA + LGPD protegen a menores de 18. El backend necesita saber el país del usuario de forma confiable para aplicar el threshold correcto.

---

## Diseño — 3 señales, todas obligatorias

| # | Señal | Fuente | Rol | Confiabilidad |
|---|---|---|---|---|
| 1 | `store_country_code` | `BillingConfig.countryCode` (Play Billing SDK) | Primaria | Más confiable — autorizada por Play Store |
| 2 | `device_country_code` | `OS.get_locale_country()` en Godot | Secundaria | Puede ser vacío (documentado en Android API) |
| 3 | `ip_country` | MaxMind GeoLite2-Country (X-Forwarded-For) | Corroboración | Nunca sobreescribe signals 1 o 2 |

**Por qué device_country_code no puede ser señal primaria:** `Locale.getCountry()` retorna `""` como valor no-error documentado (Android Locale API reference). Godot Issue #40703 / #23435 confirman casos reales: ROMs customizadas, locales sin region subtag (e.g. `en` sin `-US`).

**Por qué IP es solo corroboración:** Costo $0, sin llamada externa (offline lookup), pero puede ser VPN o red corporativa. Detectar mismatches es valioso como señal de fraude, pero no es suficientemente confiable para ser primaria.

### Función `resolve_country()`

```python
def resolve_country(store_country, device_country, ip_country) -> tuple[str | None, bool]:
    primary = store_country if valid(store_country) else device_country
    result  = primary if valid(primary) else ip_country
    mismatch = valid(primary) and valid(ip_country) and primary != ip_country
    if mismatch:
        log(primary, ip_country, threshold_change=...)  # telemetría
    return result, mismatch
```

**Decisión de diseño (2026-07-12 — Saul):** Cuando `primary` e `ip_country` discrepan y producen thresholds distintos (ej. store=US→13, IP=BR→18), **gana `primary`**. La discrepancia se loguea como telemetría (`country_signal_mismatch: bool`). Postura: seguir arquitectura; el mismatch señal potencial de VPN o cuenta de Play en otro país, no un error.

### Thresholds por país

| País | Threshold | Marco legal |
|---|---|---|
| `US` | 13 años | COPPA |
| `BR` | 18 años | Digital ECA + LGPD Art. 14 |
| Todos los demás | 13 años | Mínimo conservador |

---

## Cambios por archivo — ST-01

### `pyproject.toml`
```toml
"geoip2>=4.8",
```
Nueva dependencia aprobada por Juan Mosqueda (2026-07-12). Lookup offline, sin llamada externa en runtime.

### `app/config.py`
```python
geoip2_db_path: str = "/gcs/geolite2/GeoLite2-Country.mmdb"
```
Path del volumen GCS donde se monta el archivo .mmdb. Configurable via env var `GEOIP2_DB_PATH`.

### `app/services/geo_service.py` (nuevo)

| Función | Descripción |
|---|---|
| `consent_age_threshold(country_code)` | Retorna 13 (US/default) o 18 (BR) |
| `get_ip_country(ip, db_path)` | Async wrapper sobre lookup geoip2 |
| `resolve_country(store, device, ip)` | 3-señal resolution; retorna `(country, mismatch: bool)` |
| `_get_reader(db_path)` | Singleton lazy del `geoip2.database.Reader` — abre el .mmdb una vez por proceso, reutilizado en cada lookup |

**Graceful degradation:** Si el archivo .mmdb no existe (entorno dev sin GCS montado), `_get_reader()` retorna `None` → `get_ip_country()` retorna `None` → `resolve_country()` usa `device_country_code` como fallback. Sin crash, sin bloqueo del login.

### `app/routers/auth.py`

`LoginRequest` actualizado:
```python
# Antes:
country: str | None = None

# Después:
store_country_code: str | None = None   # Signal 1 — T-252
device_country_code: str | None = None  # Signal 2 — Godot OS.get_locale_country()
```

`login()` recibe `request: Request` para extraer `X-Forwarded-For`, llama a `geo_service`, pasa resultado a `upsert_user()`. El campo `country` en el BQ event `login_events` ahora usa `resolved_country`.

### `app/services/auth_service.py`

`upsert_user()` firma actualizada:
```python
async def upsert_user(
    db, sub, email, display_name, photo_url, provider,
    country_code: str | None = None,
    consent_age_threshold: int = 13,
    country_signal_mismatch: bool = False,
) -> tuple[str, bool]:
```

Firestore — nuevos campos en `users/{uid}.consent`:

| Campo | Tipo | Descripción |
|---|---|---|
| `country_code` | `string \| null` | País resuelto (ISO 3166-1 alpha-2) |
| `consent_age_threshold` | `int` | 13 o 18 según país |
| `country_signal_mismatch` | `bool` | True si primary e ip_country discreparon |

Usuarios existentes: se actualiza `consent.country_code`, `consent_age_threshold`, `country_signal_mismatch` en cada login (via `ref.update()` con dot-notation Firestore). Los campos de consent previos (`coppa_compliant`, `gdpr_consent`, etc.) no se tocan.

---

## ST-02 — MaxMind Refresh Pipeline ✅ Done (2026-07-13)

### Infraestructura desplegada

```
Cloud Scheduler (semanal, martes 04:00 UTC) — maxmind-geolite2-weekly
  └─► Cloud Run Job: maxmind-geolite2-refresh
        └─► imagen: maxmindinc/geoipupdate:latest
              └─► escribe GeoLite2-Country.mmdb
                    └─► GCS bucket: gs://motamaze-geolite2 (proyecto motamaze, us-central1)
                          └─► Cloud Run auth service: volume mount /gcs/geolite2 (read-only)
                                └─► prod: motamaze-backend-00048-554
                                └─► dev:  motamaze-backend-00052-6fq (cross-project IAM)
```

**Por qué GCS y no bundle en el container:** La EULA de MaxMind requiere actualizar el archivo dentro de los 30 días de cada release. GeoLite2 se actualiza 2x/semana (martes y viernes). El volume mount permite que el auth service tome el nuevo .mmdb sin redeploy.

### Recursos creados

| Recurso | ID / Nombre | Notas |
|---|---|---|
| GCS Bucket | `gs://motamaze-geolite2` | us-central1, uniform access |
| Secret Manager | `maxmind-license-key` (version 1) | License key MaxMind Account 1377358 |
| IAM prod | `game-api-backend@motamaze` → `roles/storage.objectViewer` | Bucket-level |
| IAM dev | `game-api-backend@motamaze-dev` → `roles/storage.objectViewer` | Cross-project |
| Cloud Run Job | `maxmind-geolite2-refresh` | `maxmindinc/geoipupdate:latest`, env vars: GEOIPUPDATE_ACCOUNT_ID=1377358, GEOIPUPDATE_EDITION_IDS=GeoLite2-Country, GEOIPUPDATE_DB_DIR=/gcs/geolite2; secret: GEOIPUPDATE_LICENSE_KEY |
| Cloud Scheduler | `maxmind-geolite2-weekly` | `0 4 * * 2` (martes 04:00 UTC); próxima ejecución 2026-07-14 |
| Cloud Monitoring | `projects/motamaze/alertPolicies/17855742225595716849` | Alert si Cloud Run Job falla (proxy de file-stale > 7 días) |
| .mmdb inicial | `GeoLite2-Country_20260710` (8.43 MiB) | Subida 2026-07-13 |

### Testing — ST-02 (2026-07-13)

```powershell
# Validación end-to-end: ejecución manual del Cloud Run Job
gcloud run jobs execute maxmind-geolite2-refresh --region=us-central1 --project=motamaze --wait
# Execution [maxmind-geolite2-refresh-h88t4] has successfully completed.

# Verificación del archivo en GCS
gcloud storage ls -l gs://motamaze-geolite2/
#          0  2026-07-13T03:34:26Z  gs://motamaze-geolite2/.geoipupdate.lock
#    8844154  2026-07-13T03:28:37Z  gs://motamaze-geolite2/GeoLite2-Country.mmdb
```

### Resultado
- `.geoipupdate.lock` confirma que geoipupdate gestionó el archivo correctamente
- Archivo disponible en `/gcs/geolite2/GeoLite2-Country.mmdb` para prod y dev
- Próxima actualización automática: **2026-07-14 04:00 UTC** (mañana)

### Cloud Monitoring alert
Alerta si Cloud Run Job `maxmind-geolite2-refresh` falla → detecta fallo del pipeline antes de incumplir la EULA (30 días). Policy ID: `17855742225595716849`.

---

## ST-03 — Test e2e ✅ Done (2026-07-14)

Tests 3-5 ejecutados hoy. Tests 1-2 requieren Play Billing SDK en dispositivo real + Play Console tax config + license-testing accounts — movidos a T-607 (subitem ID 12534836436, mismo gate que E2E de pagos).

Tests:
1. Cuenta configurada en US → `store_country_code=US` → `consent_age_threshold=13` → **movido a T-607**
2. Cuenta configurada en BR → `store_country_code=BR` → `consent_age_threshold=18` → **movido a T-607**
3. Sin `store_country_code` + `device_country_code=MX` → primary=MX → threshold=13 ✅ PASS
4. Sin ambos → ip_country usado como fallback ✅ PASS (5/5 IPs reales: US/BR/MX/AR/DE)
5. Mismatch: `store_country_code=US`, IP geolocated in BR → `country_signal_mismatch=true`, result=US ✅ PASS

### Resultados ST-03 tests 3-5 (2026-07-14)

```
# Tests de lógica pura — resolve_country() + consent_age_threshold()
[PASS] T3-a  resolved_country == MX
[PASS] T3-b  mismatch_flag    == False
[PASS] T3-c  threshold(MX)   == 13
[PASS] T4-a  resolved_country == DE (ip fallback)
[PASS] T4-b  mismatch_flag    == False
[PASS] T4-c  threshold(DE)    == 13 (default)
[PASS] T4-d  resolved_country == BR (ip=BR)
[PASS] T4-e  threshold(BR)    == 18
[PASS] T5-a  resolved_country == US (store_wins)
[PASS] T5-b  mismatch_flag    == True
[PASS] T5-c  threshold(US)    == 13
[PASS] T6-a  resolved_country == None (all absent)
[PASS] T6-b  threshold(None)  == 13 (default)
RESULT: 13/13 passed

# MaxMind GeoLite2 lookup real (.mmdb de GCS gs://motamaze-geolite2)
[PASS] T4-maxmind 8.8.8.8      = US
[PASS] T4-maxmind 200.216.0.1  = BR
[PASS] T4-maxmind 189.203.0.1  = MX
[PASS] T4-maxmind 200.49.0.1   = AR
[PASS] T4-maxmind 217.0.0.1    = DE
RESULT: 5/5 passed
```

---

## Testing — ST-01 Syntax check (2026-07-12)

```bash
python -c "
import ast
for f in ['app/config.py','app/services/geo_service.py',
          'app/routers/auth.py','app/services/auth_service.py']:
    ast.parse(open(f).read())
    print(f'SYNTAX OK: {f}')
"
# SYNTAX OK: app/config.py
# SYNTAX OK: app/services/geo_service.py
# SYNTAX OK: app/routers/auth.py
# SYNTAX OK: app/services/auth_service.py
```

---

## Follow-ups / Notes

- **`coppa_compliant`** permanece `False` en todos los usuarios hasta que T-406 (IARC rating) esté activo en Play Store y se haya validado el flujo de verificación de edad. El threshold almacenado es lo que habilita la lógica downstream cuando llegue el momento.
- **Datos no retenidos:** Los valores raw de `store_country_code`, `device_country_code`, `ip_country` no se persisten — solo el resultado resuelto + el flag de mismatch. Consistent con el patrón de data minimization de la arquitectura (línea 1096).
- **Thread safety de `_reader`:** Cloud Run corre múltiples procesos (no multi-thread). Cada proceso tiene su propio `_reader` singleton → sin contención.
- **EULA attribution:** "This product includes GeoLite2 data created by MaxMind, available from https://www.maxmind.com" — debe aparecer en política de privacidad (pendiente T-406 o ticket separado de privacy policy).
