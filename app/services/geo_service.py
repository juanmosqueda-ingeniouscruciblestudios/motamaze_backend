import asyncio
import logging

import geoip2.database
import geoip2.errors

logger = logging.getLogger(__name__)

# Age threshold per ISO 3166-1 alpha-2 country code.
# US: COPPA (Children's Online Privacy Protection Act) — under 13 requires parental consent.
# BR: Brazil Digital ECA (Lei 14.010/2020 + LGPD) — under 18 requires parental consent.
_AGE_THRESHOLD: dict[str, int] = {
    "US": 13,
    "BR": 18,
}
_DEFAULT_THRESHOLD = 13

_reader: geoip2.database.Reader | None = None
_reader_path: str | None = None


def consent_age_threshold(country_code: str | None) -> int:
    """Returns the minimum consent age for a given country, defaulting to 13."""
    if not country_code:
        return _DEFAULT_THRESHOLD
    return _AGE_THRESHOLD.get(country_code.upper(), _DEFAULT_THRESHOLD)


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
