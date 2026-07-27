# Config Reference — Firebase Remote Config Parameters

> Última actualización: 2026-07-27 (T-244 ST-05)
> Referenciado desde el ticket original de T-244; no existía hasta ahora.

Lista cada parámetro de Firebase Remote Config que el backend lee. Detalle de implementación
(cliente REST, cache, fallback): `logic/remote-config.md`.

---

## Parámetros

| Key | Tipo | Default (fallback si Remote Config no responde) | Qué controla | Leído por |
|---|---|---|---|---|
| `regen_interval_secs` | integer (segundos) | `1800` (30 min) | Cada cuánto se regenera 1 vida | `GET /lives`, `POST /lives/spend`, `POST /lives/grant` |
| `default_max_lives` | integer | `5` | Máximo de vidas por usuario (tope de regen y de grants) | `GET /lives`, `POST /lives/spend`, `POST /lives/grant` |

**Publicados en `motamaze-dev`** (2026-07-27, ST-05) con los mismos valores que el fallback —
`scripts/seed_remote_config.py --project motamaze-dev`. Validado end-to-end contra el Cloud Run de
dev real (ver `logic/remote-config.md` para el detalle y el hallazgo de IAM). **Prod no configurado
todavía** — deferido post soft-launch, mismo criterio que T-123/T-302/T-404/T-240.

---

## ⚠️ Prerrequisito de IAM (descubierto en ST-05, no documentado en ningún lado antes)

La cuenta de servicio del backend (`game-api-backend@<project>.iam.gserviceaccount.com`) necesita el
rol **`roles/firebase.admin`** en el proyecto para poder leer el template de Remote Config — **sin
este rol, cada fetch falla con un 403 `GET_TEMPLATE` y el backend cae silenciosamente al fallback**
(por diseño, ver `remote_config_service.get_value` — nunca lanza), sin ningún error visible fuera de
los logs de Cloud Run. No existe un rol de IAM dedicado y más granular para Remote Config (se buscó
`roles/firebaseremoteconfig.*` — no existe como rol predefinido; la API v1 de Remote Config solo
reconoce los roles clásicos de Firebase). Ya otorgado en `motamaze-dev`
(`game-api-backend@motamaze-dev.iam.gserviceaccount.com`). **Pendiente otorgarlo también en
`motamaze` (prod) antes de publicar parámetros ahí** — de lo contrario prod seguirá funcionando
(fallback = mismo valor), pero de forma silenciosamente no-tunable.

```bash
gcloud projects add-iam-policy-binding <project> \
  --member="serviceAccount:game-api-backend@<project>.iam.gserviceaccount.com" \
  --role="roles/firebase.admin" --condition=None
```

---

## Fuera de alcance de T-244 (decisión de scope, no un olvido)

| Tunable mencionado en el ticket original | Por qué no está aquí |
|---|---|
| Catálogo / promociones | T-240 ya los hace live-tunable vía Firestore (`config/catalog`, `promotions`) — Remote Config no es buen fit para su estructura anidada de productos, y agregarlo encima sería redundante |
| Niveles (`LevelData`) | Viven en recursos `.tres` de Godot — 100% cliente, el backend no tiene ningún parámetro de nivel que ajustar |

---

## Cómo agregar un nuevo parámetro

1. Confirmar que la cuenta de servicio del proyecto tiene `roles/firebase.admin` (ver arriba) — si no,
   el parámetro se publicará bien pero el backend nunca lo verá
2. Agregarlo a `PARAMETERS` en `scripts/seed_remote_config.py` y correrlo (`--project motamaze-dev` o
   `motamaze`) — no hace falta usar la consola web, aunque también funciona
3. Backend: `await remote_config_service.get_value(settings.gcp_project_id, "<key>", <default>, cast=<tipo>)`
   — siempre con un default de fallback explícito, nunca asumir que el parámetro existe
4. Agregar la fila a la tabla de arriba

---

## "Change auditing"

El ticket original pedía "change auditing" como criterio de aceptación. Se interpretó como
satisfecho por el **historial de versiones nativo de Firebase Remote Config** (consola → Remote
Config → History — cada publicación queda registrada con quién y cuándo, con posibilidad de
rollback) — **sin código de auditoría adicional en el backend**. Decisión de alcance explícita, no
un criterio omitido por accidente.
