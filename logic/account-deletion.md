# Account Deletion (T-123) — Estado actual

> Última actualización: 2026-07-22

Flujo completo de `DELETE /auth/account`: solicitud → periodo de gracia de 30 días (cancelable) →
purga real de Firestore y BigQuery. Requisito legal: GDPR Art.17 (derecho al olvido) + Apple App
Store Review 5.1.1 (toda app con creación de cuenta debe permitir borrarla desde la app).

---

## Los 4 endpoints

| Endpoint | Qué hace |
|---|---|
| `DELETE /auth/account` | Marca `delete_requested_at`, revoca la sesión actual, encola fila `status=pending` en BQ |
| `POST /auth/login` | **No bloqueado** por borrado pendiente — expone `deletion_pending: true` en la respuesta |
| `POST /auth/refresh` | **Bloqueado** (`401 AUTH_ACCOUNT_DELETION_PENDING`) si hay borrado pendiente |
| `POST /auth/account/cancel-deletion` | Limpia `delete_requested_at`, reactiva la cuenta, encola fila `status=cancelled` en BQ |
| `POST /jobs/purge-deleted-accounts` | Cloud Scheduler diario — purga cuentas con 30+ días de borrado pendiente |

---

## Por qué login se queda abierto pero refresh no

Decisión de diseño tomada durante la implementación (T-123 ST-01), no arbitraria: si `POST
/auth/login` rechazara cuentas con borrado pendiente, no habría forma de obtener un JWT para llamar
`cancel-deletion` — el sistema no tiene otro canal de identificación. Por eso:

- **Login se mantiene abierto.** `upsert_user()` (`app/services/auth_service.py`) retorna un 4to
  valor, `deletion_pending: bool`, calculado de `existing.get("delete_requested_at") is not None`
  en el branch de usuario existente. `LoginResponse.deletion_pending` lo expone para que el cliente
  muestre una pantalla de "¿cancelar borrado?" en vez del juego normal.
- **Refresh sí se bloquea.** `consume_refresh_session()` (`app/services/auth_service.py`) lee
  `users/{uid}.delete_requested_at` antes de rotar la sesión; si no es `None`, lanza
  `ValueError("AUTH_ACCOUNT_DELETION_PENDING")` — la sesión vieja **no se consume** en el rechazo
  (queda intacta, a diferencia del flujo normal que la borra al rotar). Esto es lo que realmente
  cierra el hueco de que otro dispositivo logueado pudiera seguir renovando indefinidamente después
  de solicitado el borrado.

---

## Cancelación (`POST /auth/account/cancel-deletion`)

`app/routers/auth.py`. Autenticado. `Firestore` es la fuente de verdad — limpiar
`delete_requested_at` ahí es lo que reactiva la cuenta en todos lados (el flag de login, el corte de
refresh). 404 `AUTH_NO_PENDING_DELETION` si no hay nada que cancelar, 404 `USER_NOT_FOUND` si la
cuenta ya no existe (alcanzable una vez que el purgado corrió).

`account_deletions` (BigQuery) es un log de eventos append-only, no un registro mutable — cancelar
inserta una **fila nueva** con `status="cancelled"`, no actualiza la fila `pending` original. Un
usuario puede tener varias filas en esta tabla a lo largo del tiempo (pending → cancelled → pending
→ completed, etc.) — quien lea esta tabla debe resolver el estado por la fila más reciente
(`requested_at DESC`) por `user_id`, nunca asumir una fila por usuario.

---

## Purga (`POST /jobs/purge-deleted-accounts`)

`app/routers/jobs.py`, protegido con el mismo patrón de header `X-CloudScheduler-JobName` que
`reconcile-purchases`/`admob-daily-report` (Cloud Run IAM es la capa de auth real; el header es
belt-and-suspenders). Cloud Scheduler corre esto diario contra `motamaze-dev` hoy (creado y validado
end-to-end 2026-07-22); promoción a prod es una subtarea aparte, pendiente de que el endpoint esté
desplegado ahí.

### `find_users_due_for_purge()` (`app/services/account_deletion_service.py`)

Scan completo de `users` filtrado en Python (no un query Firestore con `where(delete_requested_at
<=, cutoff)`) — escala MVP (<1,000 usuarios en soft launch), evita un índice compuesto, y evita un
query de desigualdad contra un campo que es `None` para la mayoría de los documentos.

### Orden: BigQuery primero, Firestore después

Deliberado, no arbitrario. `purge_user_firestore_data()` borra `users/{uid}` al final — es el
mismo campo que `find_users_due_for_purge()` escanea. Si el purgado de BigQuery lanzara una
excepción, el de Firestore nunca corre, así que el usuario sigue "due" y se reintenta en el
siguiente run. Ambas purgas son idempotentes (borrar/anonimizar algo ya borrado/anonimizado es un
no-op), así que reintentar tras una falla parcial siempre es seguro. El orden inverso dejaría a un
usuario huérfano: Firestore ya borrado, sin ninguna forma de reintentar su purga de BigQuery.

### Firestore — qué se borra vs. qué se anonimiza

| Colección | Tratamiento | Por qué |
|---|---|---|
| `progress`, `lives`, `entitlements`, `season_progress`, `achievement_progress` | Borrado completo | Sin necesidad de retención — estado operativo derivado |
| `sessions` (query por `uid`) | Borrado completo | Idem |
| `purchases` (query por `uid`) | **Anonimizado** — `uid: null`, `anonymized_at` agregado | Registro financiero/transaccional — retenido para auditoría contable y disputas de reembolso (GDPR Art.17(3)(b), excepción por obligación legal) |
| `users/{uid}` | Borrado completo, **al final** | Es el flag de "existe esta cuenta" — borrarlo antes haría irreversible el resto sin terminar |

`entitlements` se borra por completo, no se anonimiza como `purchases` — a diferencia de esa
colección, su doc ID **es** el uid (no hay identificador que "quitar" sin borrar el documento), y es
estado operativo derivado (qué posee el usuario hoy), no un registro de una transacción financiera.

**Excluido a propósito de este job** (no es un olvido):
- `revoked_jtis` — tiene su propio TTL de 14 días; cualquier JTI de este usuario ya expiró mucho antes de que se cumplan los 30 días de gracia.
- `shares/{token}` — el `uid` nunca es público (`GET /s/{token}` no lo incluye), y la colección ya expira sola al fin de temporada.
- `leaderboard_cache` — una entrada obsoleta dura como máximo 5 minutos (su propio intervalo de refresh de Cloud Scheduler) — se autocorrige, no vale la pena un caso especial.

### BigQuery — mismo criterio, aplicado a las tablas históricas (DATA-001)

Primer uso de DML (`UPDATE`/`DELETE`) en este codebase — todo lo anterior era streaming insert
append-only. `bq_streaming.run_dml()` envuelve la llamada bloqueante `bigquery.Client().query().result()`
vía `asyncio.to_thread`. A diferencia de `stream_event` (fire-and-forget, solo loguea errores), los
errores de `run_dml` **propagan** — el caller necesita saber si una purga falló.

| Tabla | Tratamiento |
|---|---|
| `login_events`, `session_durations`, `player_behavior`, `ad_impressions`, `entitlement_grants` | `DELETE ... WHERE user_id = @user_id` |
| `purchase_events` | `UPDATE ... SET user_id = @anon_id WHERE user_id = @user_id` |

`user_id` es `NOT NULL` en las 6 tablas — anonimizar no puede significar dejarlo en `null`. El
reemplazo es `"deleted_" + SHA256(user_id)[:16]`, determinístico (mismo uid siempre produce el mismo
hash) — las filas de un mismo usuario borrado se mantienen agrupables entre tablas/corridas para
efectos de auditoría agregada, sin ser reversible al uid real. Misma técnica que ya se usa para
hashear `purchase_token` de Android (`purchases/{doc_id}`).

`admob_daily_report` y `account_deletions` **no** están en ninguna lista — la primera es agregada
(sin columna `user_id`), la segunda es el propio log de auditoría de este borrado (borrarla
destruiría la evidencia de que el borrado ocurrió).

**Streaming buffer:** BigQuery bloquea DML sobre filas insertadas recientemente (~90 min). Como esto
corre 30 días después de la última actividad posible del usuario, no se espera que esto sea un
problema en la práctica — no validado contra un caso real todavía.

### Status final en `account_deletions`

Al terminar el loop por usuario, se encola una fila (`background_tasks`, best-effort, mismo patrón
que el resto de este codebase):
- `status="completed"`, `completed_at` seteado, `tables_purged` = unión de tablas de BigQuery + Firestore tocadas.
- `status="failed"`, `notes` con el mensaje de la excepción (truncado a 500 chars) — nunca se deja un estado intermedio silencioso.

---

## Limitaciones conocidas / a revisar

- **Streaming buffer de BigQuery no validado contra un caso real** — ver nota arriba.
- **Cloud Scheduler solo existe en DEV hoy** (2026-07-22) — promoción a PROD es una subtarea
  aparte, pendiente de que el endpoint esté desplegado ahí vía el pipeline de aprobación manual.
- **`shares`/`leaderboard_cache` no se tocan activamente** — ver razones en la tabla de exclusiones
  arriba; ambas son de bajo riesgo pero no cero.
