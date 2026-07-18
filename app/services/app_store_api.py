import asyncio
from pathlib import Path

from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload
from appstoreserverlibrary.models.ResponseBodyV2DecodedPayload import ResponseBodyV2DecodedPayload
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException, VerificationStatus

from app.config import Settings

_CERTS_DIR = Path(__file__).resolve().parent.parent / "certs" / "apple"

_root_certs: list[bytes] | None = None
_verifier: SignedDataVerifier | None = None
_verifier_key: tuple[str, str, int | None] | None = None


class AppStoreAPIError(Exception):
    def __init__(self, http_status: int, error_body: dict):
        self.http_status = http_status
        self.error_body = error_body


def _load_root_certificates() -> list[bytes]:
    global _root_certs
    if _root_certs is None:
        certs = [p.read_bytes() for p in sorted(_CERTS_DIR.glob("*.cer"))]
        if not certs:
            raise AppStoreAPIError(503, {"error": f"no Apple root certs found in {_CERTS_DIR}"})
        _root_certs = certs
    return _root_certs


def _get_verifier(settings: Settings) -> SignedDataVerifier:
    """Rebuilds the verifier only if the relevant settings change — in practice
    once per process, since get_settings() is @lru_cache'd (app/dependencies.py).
    Mirrors geo_service._get_reader's cache-invalidation pattern."""
    global _verifier, _verifier_key
    key = (settings.apple_environment, settings.apple_bundle_id, settings.apple_app_apple_id)
    if _verifier is None or _verifier_key != key:
        _verifier = SignedDataVerifier(
            _load_root_certificates(),
            enable_online_checks=True,
            environment=Environment(settings.apple_environment),
            bundle_id=settings.apple_bundle_id,
            app_apple_id=settings.apple_app_apple_id,
        )
        _verifier_key = key
    return _verifier


def _status_to_error(exc: VerificationException) -> AppStoreAPIError:
    if exc.status == VerificationStatus.RETRYABLE_VERIFICATION_FAILURE:
        return AppStoreAPIError(503, {"verification_status": exc.status.name})
    return AppStoreAPIError(402, {"verification_status": exc.status.name})


async def verify_signed_transaction(signed_transaction: str, settings: Settings) -> JWSTransactionDecodedPayload:
    """Verifies a StoreKit 2 signedTransaction JWS locally against Apple's pinned
    root certificates — no outbound call to Apple, no App Store Server API
    credentials needed. Raises AppStoreAPIError on failure."""
    verifier = _get_verifier(settings)
    try:
        return await asyncio.to_thread(verifier.verify_and_decode_signed_transaction, signed_transaction)
    except VerificationException as exc:
        raise _status_to_error(exc)


async def verify_notification(signed_payload: str, settings: Settings) -> ResponseBodyV2DecodedPayload:
    """Verifies an App Store Server Notification V2 (ASSN v2) signedPayload —
    same local, offline verification as verify_signed_transaction."""
    verifier = _get_verifier(settings)
    try:
        return await asyncio.to_thread(verifier.verify_and_decode_notification, signed_payload)
    except VerificationException as exc:
        raise _status_to_error(exc)
