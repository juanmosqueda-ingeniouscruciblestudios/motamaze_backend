"""Integration tests for /payments/ios/verify and /payments/ios/refund-notification
(T-251 / T-IOS-1 / T-254 — real Apple signed-transaction verification replacing
the stubs). SignedDataVerifier's trust chain is pinned to Apple's real root
certs, so a self-signed test JWS can never pass real verification — tests mock
app_store_api.verify_signed_transaction/verify_notification at the module
boundary instead (same precedent as test_auth_router.py mocking
auth_service.verify_google_token), and assert on the router's own logic:
idempotency, entitlement granting, error mapping, and the `platform` field."""

from appstoreserverlibrary.models.Data import Data
from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.models.ResponseBodyV2DecodedPayload import ResponseBodyV2DecodedPayload
from appstoreserverlibrary.signed_data_verifier import VerificationStatus

from app.services import app_store_api, jwt_service

VERIFY_URL = "/payments/ios/verify"
REFUND_URL = "/payments/ios/refund-notification"


def _auth_headers(test_settings, uid: str = "user-ios-1") -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="apple",
        session_id="session-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


def _fake_transaction(
    transaction_id: str = "2000000123456789",
    product_id: str = "no_ads",
    revocation_date: int | None = None,
) -> JWSTransactionDecodedPayload:
    return JWSTransactionDecodedPayload(
        transactionId=transaction_id,
        productId=product_id,
        revocationDate=revocation_date,
    )


def _mock_verify_transaction(monkeypatch, transaction: JWSTransactionDecodedPayload):
    async def _fake(signed_transaction, settings):
        return transaction

    monkeypatch.setattr(app_store_api, "verify_signed_transaction", _fake)


def _mock_verify_transaction_error(monkeypatch, http_status: int):
    async def _fake(signed_transaction, settings):
        raise app_store_api.AppStoreAPIError(http_status, {"verification_status": "X"})

    monkeypatch.setattr(app_store_api, "verify_signed_transaction", _fake)


# ---------------------------------------------------------------------------
# ios_verify — happy path per entitlement type
# ---------------------------------------------------------------------------


async def test_ios_verify_grants_no_ads_and_sets_platform(client, fake_db, test_settings, monkeypatch):
    _mock_verify_transaction(monkeypatch, _fake_transaction(transaction_id="tx-no-ads", product_id="no_ads"))

    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "irrelevant-mocked", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["grant_status"] == "granted"
    assert body["entitlement"]["type"] == "no_ads"

    purchase_doc = (await fake_db.collection("purchases").document("tx-no-ads").get()).to_dict()
    assert purchase_doc["platform"] == "ios"
    assert purchase_doc["acknowledged"] is True

    entitlements = (await fake_db.collection("entitlements").document("user-ios-1").get()).to_dict()
    assert entitlements["no_ads"] is True


async def test_ios_verify_grants_skin(client, fake_db, test_settings, monkeypatch):
    _mock_verify_transaction(monkeypatch, _fake_transaction(transaction_id="tx-skin", product_id="skin_gold"))

    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "irrelevant-mocked", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 200
    entitlements = (await fake_db.collection("entitlements").document("user-ios-1").get()).to_dict()
    assert "skin_gold" in entitlements["skins"]


async def test_ios_verify_grants_season_pass(client, fake_db, test_settings, monkeypatch):
    _mock_verify_transaction(
        monkeypatch, _fake_transaction(transaction_id="tx-season", product_id="season_pass_gold")
    )

    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "irrelevant-mocked", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 200
    season = (await fake_db.collection("season_progress").document("user-ios-1").get()).to_dict()
    assert season["has_gold_pass"] is True


async def test_ios_verify_grants_life_pack(client, fake_db, test_settings, monkeypatch):
    _mock_verify_transaction(
        monkeypatch, _fake_transaction(transaction_id="tx-lives", product_id="lives_pack_5")
    )

    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "irrelevant-mocked", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 200
    assert resp.json()["entitlement"]["current_lives"] == 5
    lives = (await fake_db.collection("lives").document("user-ios-1").get()).to_dict()
    assert lives["count"] == 5


# ---------------------------------------------------------------------------
# ios_verify — error paths
# ---------------------------------------------------------------------------


async def test_ios_verify_unknown_product(client, test_settings, monkeypatch):
    _mock_verify_transaction(monkeypatch, _fake_transaction(product_id="totally_unknown_sku"))
    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "irrelevant-mocked", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "PAY_PRODUCT_NOT_FOUND"


async def test_ios_verify_revoked_transaction_rejected(client, test_settings, monkeypatch):
    _mock_verify_transaction(
        monkeypatch, _fake_transaction(product_id="no_ads", revocation_date=1700000000000)
    )
    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "irrelevant-mocked", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["error_code"] == "PAY_VERIFICATION_FAILED"


async def test_ios_verify_verification_failure_maps_to_402(client, test_settings, monkeypatch):
    _mock_verify_transaction_error(monkeypatch, 402)
    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "garbage", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["error_code"] == "PAY_VERIFICATION_FAILED"


async def test_ios_verify_retryable_failure_maps_to_503(client, test_settings, monkeypatch):
    _mock_verify_transaction_error(monkeypatch, 503)
    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "garbage", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error_code"] == "PAY_STORE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# ios_verify — idempotency
# ---------------------------------------------------------------------------


async def test_ios_verify_idempotent_no_double_grant(client, fake_db, test_settings, monkeypatch):
    fake_db.seed("purchases", "tx-existing", {
        "uid": "user-ios-1", "platform": "ios", "product_id": "no_ads",
        "product_type": "non_consumable", "acknowledged": True, "created_at": None,
    })
    _mock_verify_transaction(monkeypatch, _fake_transaction(transaction_id="tx-existing", product_id="no_ads"))

    resp = await client.post(
        VERIFY_URL,
        json={"signed_transaction": "irrelevant-mocked", "session_id": "s1"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 200
    assert resp.json()["grant_status"] == "already_granted"
    # entitlements collection was never touched — no double grant
    assert "entitlements" not in fake_db._collections or not fake_db._collections["entitlements"]


# ---------------------------------------------------------------------------
# ios_refund_notification
# ---------------------------------------------------------------------------


def _mock_verify_notification(monkeypatch, notification: ResponseBodyV2DecodedPayload):
    async def _fake(signed_payload, settings):
        return notification

    monkeypatch.setattr(app_store_api, "verify_notification", _fake)


async def test_ios_refund_revokes_and_marks_voided(client, fake_db, monkeypatch):
    fake_db.seed("purchases", "tx-refund-1", {
        "uid": "user-ios-1", "platform": "ios", "product_id": "no_ads",
        "product_type": "non_consumable", "acknowledged": True, "created_at": None,
    })
    fake_db.seed("entitlements", "user-ios-1", {"no_ads": True})

    notification = ResponseBodyV2DecodedPayload(
        notificationType=NotificationTypeV2.REFUND,
        data=Data(signedTransactionInfo="nested-jws"),
    )
    _mock_verify_notification(monkeypatch, notification)
    _mock_verify_transaction(monkeypatch, _fake_transaction(transaction_id="tx-refund-1", product_id="no_ads"))

    resp = await client.post(REFUND_URL, json={"signedPayload": "outer-jws"})
    assert resp.status_code == 204

    purchase = (await fake_db.collection("purchases").document("tx-refund-1").get()).to_dict()
    assert purchase["voided"] is True

    entitlements = (await fake_db.collection("entitlements").document("user-ios-1").get()).to_dict()
    assert entitlements["no_ads"] is False


async def test_ios_refund_malformed_body(client):
    resp = await client.post(REFUND_URL, content=b"not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 204


async def test_ios_refund_verification_failure(client, monkeypatch):
    async def _fake(signed_payload, settings):
        raise app_store_api.AppStoreAPIError(402, {"verification_status": "X"})

    monkeypatch.setattr(app_store_api, "verify_notification", _fake)
    resp = await client.post(REFUND_URL, json={"signedPayload": "garbage"})
    assert resp.status_code == 204


async def test_ios_refund_unknown_transaction(client, monkeypatch):
    notification = ResponseBodyV2DecodedPayload(
        notificationType=NotificationTypeV2.REFUND,
        data=Data(signedTransactionInfo="nested-jws"),
    )
    _mock_verify_notification(monkeypatch, notification)
    _mock_verify_transaction(monkeypatch, _fake_transaction(transaction_id="tx-does-not-exist"))

    resp = await client.post(REFUND_URL, json={"signedPayload": "outer-jws"})
    assert resp.status_code == 204


async def test_ios_refund_already_voided_no_double_revoke(client, fake_db, monkeypatch):
    fake_db.seed("purchases", "tx-already-voided", {
        "uid": "user-ios-1", "platform": "ios", "product_id": "no_ads",
        "product_type": "non_consumable", "voided": True,
    })
    fake_db.seed("entitlements", "user-ios-1", {"no_ads": False})

    notification = ResponseBodyV2DecodedPayload(
        notificationType=NotificationTypeV2.REFUND,
        data=Data(signedTransactionInfo="nested-jws"),
    )
    _mock_verify_notification(monkeypatch, notification)
    _mock_verify_transaction(
        monkeypatch, _fake_transaction(transaction_id="tx-already-voided", product_id="no_ads")
    )

    resp = await client.post(REFUND_URL, json={"signedPayload": "outer-jws"})
    assert resp.status_code == 204
    # still false, untouched — no error, no double-revoke side effects
    entitlements = (await fake_db.collection("entitlements").document("user-ios-1").get()).to_dict()
    assert entitlements["no_ads"] is False


async def test_ios_refund_ignores_non_refund_notifications(client, fake_db, monkeypatch):
    notification = ResponseBodyV2DecodedPayload(
        notificationType=NotificationTypeV2.DID_RENEW,
        data=Data(signedTransactionInfo="nested-jws"),
    )
    _mock_verify_notification(monkeypatch, notification)

    resp = await client.post(REFUND_URL, json={"signedPayload": "outer-jws"})
    assert resp.status_code == 204
    assert not fake_db._collections.get("purchases")


# ---------------------------------------------------------------------------
# android_verify regression — platform field addition
# ---------------------------------------------------------------------------


async def test_android_verify_writes_platform_field(client, fake_db, test_settings, monkeypatch):
    from app.services import play_api

    async def _fake_get_product_purchase(pkg, product_id, purchase_token):
        return {"purchaseState": 0, "orderId": "order-1", "acknowledgementState": 0}

    async def _fake_ack(pkg, product_id, purchase_token):
        return None

    monkeypatch.setattr(play_api, "get_product_purchase", _fake_get_product_purchase)
    monkeypatch.setattr(play_api, "acknowledge_product_purchase", _fake_ack)

    resp = await client.post(
        "/payments/android/verify",
        json={"purchase_token": "tok-abc", "product_id": "no_ads", "session_id": "s1"},
        headers=_auth_headers(test_settings, uid="user-android-1"),
    )
    assert resp.status_code == 200

    import hashlib

    token_hash = hashlib.sha256(b"tok-abc").hexdigest()
    purchase = (await fake_db.collection("purchases").document(token_hash).get()).to_dict()
    assert purchase["platform"] == "android"
