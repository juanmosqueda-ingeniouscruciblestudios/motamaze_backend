import asyncio
import logging
import re
from datetime import datetime

import geoip2.database
import geoip2.errors

logger = logging.getLogger(__name__)

# Age threshold per ISO 3166-1 alpha-2 country code.
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

_reader: geoip2.database.Reader | None = None
_reader_path: str | None = None


def consent_age_threshold(country_code: str | None) -> int:
    """Returns the minimum consent age for a given country, defaulting to 13."""
    if not country_code:
        return _DEFAULT_THRESHOLD
    return _AGE_THRESHOLD.get(country_code.upper(), _DEFAULT_THRESHOLD)


# T-402 — Brazil store/OS age-signal reconciliation.
#
# Digital ECA prohibits self-declared age in Brazil, so a store/OS age-band
# signal (Apple Declared Age Range / Google Play Age Signals) must take
# priority over the DOB-based flow (T-401) there. DOB remains the ONLY
# signal for every other country — none of this is consulted outside BR.

_AGE_BAND_RE = re.compile(r"^(\d+)(?:-(\d+))?\+?$")


def store_age_signal_is_minor(signal: str | None, threshold: int) -> bool | None:
    """Conservative interpretation of a raw store/OS age-band signal.

    Returns True if the band's lower bound is below `threshold` (possibly a
    minor — err toward protecting), False if the lower bound is >= threshold
    (confirmed not a minor), None if absent/unparseable (caller falls back to
    DOB). Real-world Apple Declared Age Range / Play Age Signals band formats
    aren't confirmed yet — extend the regex once a real client payload is seen.
    """
    if not signal:
        return None
    m = _AGE_BAND_RE.match(signal.strip())
    if not m:
        return None
    lower = int(m.group(1))
    return lower < threshold


def age_gate_update(is_child: bool, now: datetime) -> dict:
    """The consent/restricted_features fields written whenever an age
    determination is made — shared by the DOB path (POST /auth/age-verify)
    and the BR store-signal path (upsert_user), so both stay consistent."""
    update: dict = {
        "consent.is_child": is_child,
        "restricted_features": {
            "leaderboard": is_child,
            "personalized_ads": is_child,
            "share_score": is_child,
        },
    }
    if not is_child:
        update["consent.coppa_compliant"] = True
    return update


def _get_reader(db_path: str) -> geoip2.database.Reader | None:
    global _reader, _reader_path
    if _reader is None or _reader_path != db_path:
        try:
            _reader = geoip2.database.Reader(db_path)
            _reader_path = db_path
        except FileNotFoundError:
            logger.warning("geo_service: GeoLite2 db not found at %s — IP lookup disabled", db_path)
            return None
        except Exception as exc:
            logger.error("geo_service: failed to open GeoLite2 db: %s", exc)
            return None
    return _reader


def _lookup_country_sync(db_path: str, ip: str) -> str | None:
    reader = _get_reader(db_path)
    if reader is None:
        return None
    try:
        return reader.country(ip).country.iso_code
    except geoip2.errors.AddressNotFoundError:
        return None
    except Exception as exc:
        logger.warning("geo_service: lookup failed ip=%.8s err=%s", ip, exc)
        return None


async def get_ip_country(ip: str, db_path: str) -> str | None:
    """Async wrapper around the synchronous geoip2 lookup."""
    return await asyncio.to_thread(_lookup_country_sync, db_path, ip)


def resolve_country(
    store_country: str | None,
    device_country: str | None,
    ip_country: str | None,
) -> tuple[str | None, bool]:
    """
    Resolves the authoritative country from three signals.

    Signal authority (highest → lowest):
      1. store_country  — Google Play BillingConfig.countryCode
      2. device_country — Godot OS.get_locale_country()
      3. ip_country     — MaxMind GeoLite2 (corroboration only, never primary)

    Returns (resolved_country, mismatch_detected).
    mismatch_detected is True when primary and ip_country are both valid but disagree —
    used as a fraud/VPN telemetry signal, not to change the resolution outcome.
    """
    def valid(c: str | None) -> bool:
        return bool(c and len(c) == 2 and c.isalpha())

    primary = store_country if valid(store_country) else (device_country if valid(device_country) else None)
    result = primary if valid(primary) else (ip_country if valid(ip_country) else None)

    mismatch = (
        valid(primary) and valid(ip_country)
        and primary.upper() != ip_country.upper()  # type: ignore[union-attr]
    )
    if mismatch:
        threshold_change = consent_age_threshold(primary) != consent_age_threshold(ip_country)
        logger.info(
            "geo_service: signal mismatch primary=%s ip=%s threshold_change=%s",
            primary, ip_country, threshold_change,
        )

    return (result.upper() if result else None), mismatch
