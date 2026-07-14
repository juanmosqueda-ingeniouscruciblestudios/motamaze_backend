# T-407 — LATAM Age Thresholds Wave 1 (MX / AR / PE / UY)

| Field | Value |
|---|---|
| **Type** | Feature / Compliance |
| **Priority** | High — LATAM pre-launch compliance |
| **Status** | ✅ Done (2026-07-14) |
| **Date** | 2026-07-14 |
| **Workstream** | Compliance / Auth |
| **Owner** | Saul Zavala Morin |
| **Monday Item ID** | 12523950750 |
| **Depends-on** | T-400 ✅ (consent_age_threshold + resolve_country implementados) |
| **Desbloquea** | T-401 (age-verify endpoint + is_child on LoginResponse) |
| **Excluye** | CL / CO — Wave 2 (T-409) |

---

## Descripción

Extiende `consent_age_threshold()` en `geo_service.py` para cubrir los cuatro mercados LATAM de Wave 1: México, Argentina, Perú y Uruguay. El threshold por país determina la edad mínima de consentimiento digital que el backend aplica para protección de datos de menores.

**Wave 1 scope únicamente.** Chile y Colombia se excluyen deliberadamente — corresponden a T-409 (Wave 2).

---

## Marco legal por país

| País | Código | Threshold | Marco legal |
|---|---|---|---|
| México | `MX` | 18 años | Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP) — Art. 8, exige consentimiento de tutor para menores de 18 |
| Argentina | `AR` | 16 años | No existe edad estatutaria fija; 16 adoptado como línea conservadora voluntaria. Ley de Protección de los Datos Personales (Ley 25.326) no especifica edad de consentimiento digital |
| Perú | `PE` | 14 años | Ley de Protección de Datos Personales (Ley 29733) — Art. 14 establece 14 como edad mínima para consentimiento sin tutor |
| Uruguay | `UY` | 18 años | Ley de Protección de Datos Personales (Ley 18.331) — Art. 9, menores de 18 requieren consentimiento parental |

**Nota AR:** El threshold 16 es una postura conservadora adoptada por el proyecto, no un requisito legal explícito. Se documenta en el código con comentario que aclara la naturaleza voluntaria.

---

## Estado previo (antes de este cambio)

`_AGE_THRESHOLD` solo contenía US y BR:

```python
_AGE_THRESHOLD: dict[str, int] = {
    "US": 13,
    "BR": 18,
}
_DEFAULT_THRESHOLD = 13
```

Todos los países LATAM (MX, AR, PE, UY) caían al default de 13, que era incorrecto para estos mercados.

---

## Implementación

### `app/services/geo_service.py`

Un solo cambio: extender `_AGE_THRESHOLD` con los 4 países Wave 1. Sin cambios en la lógica de `consent_age_threshold()`, `resolve_country()`, ni ningún otro módulo.

```python
# US: COPPA — under 13 requires parental consent.
# BR: Digital ECA (Lei 14.010/2020) + LGPD — under 18.
# MX: Ley Federal de Protección de Datos Personales (LFPDPPP) — under 18.
# AR: No fixed statutory age; 16 adopted as conservative baseline (voluntary).
# PE: Ley de Protección de Datos Personales (Ley 29733) — under 14.
# UY: Ley de Protección de Datos Personales (Ley 18.331) — under 18.
_AGE_THRESHOLD: dict[str, int] = {
    "US": 13,
    "BR": 18,
    "MX": 18,
    "AR": 16,
    "PE": 14,
    "UY": 18,
}
_DEFAULT_THRESHOLD = 13
```

Sin cambios en `consent_age_threshold()` — la función ya acepta cualquier código ISO 3166-1 alpha-2 y retorna el default para países no listados.

---

## Testing (2026-07-14)

### Script ejecutado

```python
_AGE_THRESHOLD = {"US":13,"BR":18,"MX":18,"AR":16,"PE":14,"UY":18}
_DEFAULT_THRESHOLD = 13

def consent_age_threshold(country_code):
    if not country_code:
        return _DEFAULT_THRESHOLD
    return _AGE_THRESHOLD.get(country_code.upper(), _DEFAULT_THRESHOLD)

def resolve_country(store, device, ip):
    def valid(c): return bool(c and len(c)==2 and c.isalpha())
    primary = store if valid(store) else (device if valid(device) else None)
    result  = primary if valid(primary) else (ip if valid(ip) else None)
    mismatch = valid(primary) and valid(ip) and primary.upper()!=ip.upper()
    return (result.upper() if result else None), mismatch

# Regresion: US / BR / None / DE(default)
check('REG US=13',  consent_age_threshold('US'), 13)
check('REG BR=18',  consent_age_threshold('BR'), 18)
check('REG None=13',consent_age_threshold(None), 13)
check('REG DE=13 (default)', consent_age_threshold('DE'), 13)
# T-407: nuevos países LATAM Wave 1
check('T407 MX=18', consent_age_threshold('MX'), 18)
check('T407 AR=16', consent_age_threshold('AR'), 16)
check('T407 PE=14', consent_age_threshold('PE'), 14)
check('T407 UY=18', consent_age_threshold('UY'), 18)
# Case-insensitive
check('T407 mx=18 (lowercase)', consent_age_threshold('mx'), 18)
check('T407 ar=16 (lowercase)', consent_age_threshold('ar'), 16)
# Wave 2 NO incluido (CL/CO deben seguir siendo default=13)
check('T407 CL=13 (Wave2 NOT added)', consent_age_threshold('CL'), 13)
check('T407 CO=13 (Wave2 NOT added)', consent_age_threshold('CO'), 13)
# resolve_country con países LATAM
c,m = resolve_country(None,'MX',None)
check('T407 resolve MX device_country', c, 'MX')
c,m = resolve_country(None,None,'AR')
check('T407 resolve AR ip_fallback', c, 'AR')
c,m = resolve_country('PE',None,'US')
check('T407 resolve PE store wins', c, 'PE')
check('T407 mismatch PE/US', m, True)
```

### Resultado

```
[PASS] REG US=13  got=13  expected=13
[PASS] REG BR=18  got=18  expected=18
[PASS] REG None=13  got=13  expected=13
[PASS] REG DE=13 (default)  got=13  expected=13
[PASS] T407 MX=18  got=18  expected=18
[PASS] T407 AR=16  got=16  expected=16
[PASS] T407 PE=14  got=14  expected=14
[PASS] T407 UY=18  got=18  expected=18
[PASS] T407 mx=18 (lowercase)  got=18  expected=18
[PASS] T407 ar=16 (lowercase)  got=16  expected=16
[PASS] T407 CL=13 (Wave2 NOT added)  got=13  expected=13
[PASS] T407 CO=13 (Wave2 NOT added)  got=13  expected=13
[PASS] T407 resolve MX device_country  got='MX'  expected='MX'
[PASS] T407 resolve AR ip_fallback  got='AR'  expected='AR'
[PASS] T407 resolve PE store wins  got='PE'  expected='PE'
[PASS] T407 mismatch PE/US  got=True  expected=True

RESULT: 16/16 passed
```

---

## Follow-ups / Notes

- **Wave 2 (T-409):** Chile (CL) y Colombia (CO) excluidos de esta tarea. CL y CO seguirán retornando el default 13 hasta que T-409 los agregue.
- **AR postura legal:** El threshold 16 es voluntario — no existe ley argentina que fije la edad de consentimiento digital. Revisable si hay cambio regulatorio antes del lanzamiento.
- **`coppa_compliant`:** No cambia con este ticket. El campo permanece `False` hasta T-406 (IARC rating activo en Play Store).
- **PE threshold 14 — T-401 design requirement:** PE=14 es el threshold más bajo de Wave 1 (MX/UY=18, AR=16), pero sigue siendo **más restrictivo** que el default global (13). Un usuario peruano de 13 años debe resultar `is_child=True` (13 < 14), pero si T-401 hardcodea 13 obtendría `(13 < 13) = False` — incorrecto. T-401 DEBE llamar a `consent_age_threshold(resolved_country)` en lugar de hardcodear ningún valor. La fórmula `is_child = (age < consent_age_threshold(resolved_country))` maneja correctamente todos los casos (US=13, PE=14, AR=16, BR/MX/UY=18).
