# T-406 — IARC Content Rating: globalratings.com + ClassInd mapping

| Field | Value |
|---|---|
| **Type** | Compliance / Administrative |
| **Priority** | High — No-Go before Play Store submission |
| **Status** | In Progress — ST-01 ✅ IARC questionnaire completo + ratings obtenidos (2026-07-13); ST-02 ⬜ backend `coppa_compliant` flag activation (post T-400 ST-03) |
| **Date** | 2026-07-13 |
| **Workstream** | Compliance |
| **Depends-on** | T-400 ST-01 ✅ (country resolution + consent_age_threshold) |
| **Desbloquea** | App Store submission (ratings requeridos); `coppa_compliant` flag en backend |
| **Architecture ref** | `rnd_research/2026-06-04_motamaze-architecture-final.md` lines 1225–1228, 1295–1296 |

---

## Descripción

Obtener la clasificación de contenido IARC antes de cualquier submission a Play Store o App Store. IARC es un sistema unificado que genera ratings de múltiples autoridades regionales con un solo cuestionario.

**Por qué es un No-Go antes del lanzamiento:** Play Console y App Store Connect requieren una clasificación de contenido activa antes de poder publicar la app. Adicionalmente, el rating IARC habilita la lógica downstream de `coppa_compliant` en el backend (actualmente `False` hardcodeado hasta que el flujo de verificación de edad esté validado).

---

## ST-01 — Cuestionario IARC en Play Console ✅ Done (2026-07-13)

### Dónde se completa

El cuestionario IARC **no** se completa en globalratings.com (sitio informativo). Se accede desde **Play Console**:

```
Play Console → MotaMaze → Monitor and improve
  → Policy and programs → App content → Content ratings
  → "Start questionnaire"
```

### Respuestas del cuestionario

**Step 1 — Category:**

| Campo | Valor |
|---|---|
| Email address | `saulmorin@ingeniouscruciblestudios.com` |
| Category | **Game** |
| Terms and conditions | ✅ Aceptados |

**Step 2 — Questionnaire (Game):**

| Sección | Respuesta | Razón |
|---|---|---|
| Violence, Blood, or Gory Images | **No** | Personajes cartoon sin sangre ni gore |
| Fear | **No** | Sin horror ni imagery aterradora |
| Sexuality, Suggestiveness, or Dating Games | **No** | Ninguno |
| Gambling Themes, Simulated Gambling, or Real Gambling | **No** | IAPs son compras directas (skins, no-ads) — sin loot boxes |
| Language | **No** | Sin lenguaje ofensivo |
| Controlled Substance | **No** | Sin drogas/alcohol/tabaco |
| Crude Humor | **No** | Ninguno |
| Digital Purchases, Cash Convertible Rewards, or NFTs | **Yes** | IAPs presentes |
| → Purchases of digital goods | ✅ | Skins cosméticos + "no ads" IAP |
| → Cash Convertible Rewards | ☐ | No aplica |
| → NFTs | ☐ | No aplica |
| → Random items / loot boxes | **No** | Compras directas, sin aleatoriedad |
| → Player-to-player trading | **No** | Sin intercambio entre jugadores |
| Miscellaneous — User interaction (voice/text/images) | **No** | Share de score es one-way, sin comunicación entre usuarios |
| Miscellaneous — Precise physical location sharing | **No** | No |
| Miscellaneous — Nazi symbols / propaganda | **No** | No |
| Miscellaneous — Korean national identity content | **No** | No |
| Miscellaneous — Terrorism advocacy | **No** | No |
| Miscellaneous — Realistic crime descriptions | **No** | No |

### Ratings obtenidos

| Región | Autoridad | Rating | Notas |
|---|---|---|---|
| North America | ESRB | **Everyone (E)** | ✅ Esperado |
| Europe | PEGI | **PEGI 3** | ✅ Esperado |
| Germany | USK | **All ages (USK 0)** | ✅ Esperado |
| Australia | ACB | **General (G)** | ✅ Esperado |
| South Korea | GRAC | **All ages** | ✅ Esperado |
| Taiwan | DGSC | **General Public** | ✅ Esperado |
| Saudi Arabia | Gmedia | **3** | ✅ Esperado |
| Rest of World | IARC Generic | **3+** | ✅ Esperado |
| Russia | Google Play | **3+** | ✅ Esperado |
| **Brazil** | **ClassInd** | ⚠️ **14+** | Inesperado — ver nota abajo |

### Brasil ClassInd 14+ — análisis

**Esperado:** ClassInd "Livre" (libre para todos).
**Obtenido:** ClassInd 14+.

**Causa:** ClassInd aplica automáticamente ratings elevados a juegos con in-app purchases (compras de bienes digitales). Este es un comportamiento documentado del sistema ClassInd para IAPs — no está relacionado con el contenido del juego sino con la mecánica de monetización.

**Impacción:** No es un bloqueador. Dos sistemas independientes:
- **Store rating (ClassInd 14+):** Lo que Play Store muestra como recomendación de edad en Brasil. Usuarios menores de 14 pueden descargar la app (no es un bloqueo de acceso), pero Play Store muestra la clasificación 14+.
- **Backend compliance threshold (BR=18 per T-400):** La lógica de parental consent, child-directed ads y restricted features que implementamos en T-400. Esta sigue siendo correcta e independiente del rating de tienda.

**Decisión (2026-07-13 — Saul):** Aceptar ClassInd 14+. El rating de tienda no contradice nuestra postura de compliance — de hecho, es más conservador para BR, lo cual es consistente con nuestra postura LGPD/Digital ECA. No se requiere acción adicional.

### Estado en Play Console

Ratings guardados en Play Console bajo "Changes not yet submitted for review → App content → Content Rating: Submit new questionnaire". El botón "Send app for review" permanece gris hasta que se completen los campos requeridos del store listing (primera submission completa de la app). Los ratings se incluirán automáticamente en la primera submission.

---

## ST-02 — Backend `coppa_compliant` flag activation ⬜ Pending T-400 ST-03

El campo `coppa_compliant` en `users/{uid}.consent` está hardcodeado a `False` en `app/services/auth_service.py` hasta que:

1. T-406 ratings estén activos en Play Store (post primera submission) ✅ Prerequisito cumplido
2. T-400 ST-03 esté completo (e2e test con Play Console license-testing accounts — pending Play Console tax config ~2026-07-18)
3. El flujo de verificación de edad del cliente (Godot) esté validado end-to-end

Una vez validado, `coppa_compliant` se derivará de `age_verified_at IS NOT NULL AND age >= consent_age_threshold`.

---

## Follow-ups / Notes

- **EULA attribution MaxMind** (de T-400): "This product includes GeoLite2 data created by MaxMind, available from https://www.maxmind.com" debe aparecer en la Privacy Policy (pendiente T-405).
- **iOS:** IARC para App Store Connect se completa de forma similar dentro de App Store Connect → App Information → Content Rights. Pendiente para cuando haya build de iOS.
- **ClassInd 14+ revisión:** Si en el futuro se eliminan los IAPs de la versión base del juego (modelo freemium sin compras), el cuestionario puede re-completarse para obtener "Livre". No aplica para el MVP.
- **Arquitectura ref line 1203:** "Brazil uses ClassInd; the IARC questionnaire maps to a ClassInd 'Livre' classification" — este dato en la arquitectura era una predicción incorrecta. El rating real es 14+ por IAPs. La arquitectura debe actualizarse en una revisión futura.
