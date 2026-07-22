# Age Assurance & Consent — Estado actual

> Última actualización: 2026-07-22 (T-402 subtask 5)

Cómo se determina `is_child`, `restricted_features` y `coppa_compliant` para un usuario, y de dónde
sale cada señal. Tres señales distintas alimentan esto — **no confundirlas**:

| Señal | De dónde sale | Cubre |
|---|---|---|
| `country_code` | `geo_service.resolve_country()` — 3 señales (store/device/IP), resuelto en cada `POST /auth/login` | Determina el **umbral de edad aplicable** (`consent_age_threshold`), no la edad en sí |
| DOB autodeclarado | Cliente → `POST /auth/age-verify` (T-401) | Señal **primaria en todo el mundo excepto Brasil**; secundaria/fallback en Brasil |
| `store_age_signal` | Cliente → `POST /auth/login` (T-402) — Apple Declared Age Range (iOS) / Google Play Age Signals (Android) | Señal **primaria y obligatoria en Brasil** (Digital ECA prohíbe autodeclaración); no se usa en ningún otro país |

---

## Umbral de edad por país (`geo_service.consent_age_threshold`)

```python
_AGE_THRESHOLD = {"US": 13, "BR": 18, "MX": 18, "AR": 16, "PE": 14, "UY": 18}
_DEFAULT_THRESHOLD = 13
```
Resuelto en cada login vía `resolve_country(store_country_code, device_country_code, ip_country)` (prioridad: store > device > IP) y guardado en `consent.country_code` / `consent.consent_age_threshold`.

## Rama 1 — Todo país excepto Brasil (sin cambio desde T-401)

`is_child` queda en `null` hasta que el cliente llama `POST /auth/age-verify` con el DOB. Ahí:
```python
age = today - dob  # con día descartado por minimización de datos
is_child = age < consent_age_threshold
```
Se escribe `consent.is_child`, `restricted_features` (`leaderboard`/`personalized_ads`/`share_score`, todos `= is_child`), y `consent.coppa_compliant = True` solo si el usuario es adulto. `consent.age_verified_at` siempre se actualiza.

## Rama 2 — Brasil (T-402, agregado 2026-07-22)

En Brasil, `store_age_signal` (enviado en `POST /auth/login`, ver `docs/DATA_MODEL.md`) **manda sobre el DOB**. Interpretación conservadora vía `geo_service.store_age_signal_is_minor(signal, threshold)`:

```python
_AGE_BAND_RE = re.compile(r"^(\d+)(?:-(\d+))?\+?$")
# el límite INFERIOR de la banda decide — "13-15" -> 13 < 18 -> menor
# "18+" -> 18, no < 18 -> no menor. Formato no reconocido -> None (cae a DOB).
```

**Dónde se aplica:**
- **`upsert_user()` (login, `app/services/auth_service.py`):** si `country_code == "BR"` y `store_age_signal` es parseable, `is_child`/`restricted_features`/`coppa_compliant` se establecen **inmediatamente en el login** — no se espera a `age-verify`. Esto cierra el hueco de "assurance debe ser upstream, requerido para todos en BR" del doc de arquitectura (antes, un usuario BR quedaba sin restricciones hasta un paso posterior opcional).
- **`POST /auth/age-verify`:** si el usuario es de Brasil y ya tiene una `store_age_signal` parseable, el DOB **no puede sobreescribir** `is_child`/`restricted_features`/`coppa_compliant` — solo se actualiza `age_verified_at` (bookkeeping). Si no hay señal parseable (cliente viejo, o plataforma no la devolvió), el flujo DOB de la Rama 1 corre exactamente igual que hoy.

**Helper compartido** (`geo_service.age_gate_update(is_child, now)`) — usado por ambos call sites para que la forma del update (`consent.is_child`, `restricted_features`, `consent.coppa_compliant`) sea idéntica sin importar qué señal decidió.

**Reevaluación en logins repetidos:** si un usuario BR loguea sin señal la primera vez (queda en `is_child=null`, como Rama 1) y en un login posterior el cliente sí manda la señal, se reconcilia en ese momento — no hace falta esperar a `age-verify`.

## Limitaciones conocidas / a revisar

- **Formato de banda no confirmado con un payload real** de Apple/Google — el regex cubre `"13-15"`, `"18+"`, `"17"`; si el formato real difiere, `store_age_signal_is_minor` devuelve `None` (fallback seguro a DOB) en vez de fallar.
- **Provisional pendiente de guía final de ANPD** (ver `docs/DATA_MODEL.md` y el comentario en T-402/Monday) — revisar antes de escalar en Brasil.
- **Cliente (Godot) todavía no envía `store_age_signal`** — hasta que Juan integre las APIs nativas (T-402 subtasks 6-8), todo usuario BR sigue cayendo en el fallback DOB de la Rama 1, sin cambio de comportamiento visible todavía.
