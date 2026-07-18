"""Shared test fixtures: an in-memory Firestore double, RSA keypairs for signing
test JWTs (app-issued access tokens + fake Apple identity tokens), and an
httpx test client with dependencies overridden so tests never touch GCP."""

import base64
import copy
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from google.cloud.firestore_v1.transforms import ArrayUnion
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings
from app.main import app
from app.services import auth_service, jwt_service

# ---------------------------------------------------------------------------
# In-memory Firestore double
# ---------------------------------------------------------------------------


class FakeDocSnapshot:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = copy.deepcopy(data) if data is not None else None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict | None:
        return copy.deepcopy(self._data) if self._data is not None else None


def _set_nested(store: dict, dotted_key: str, value) -> None:
    parts = dotted_key.split(".")
    cur = store
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _resolve_value(value, existing_value):
    """Resolves Firestore field-transform sentinels (currently just ArrayUnion,
    the only one this codebase uses) against the previously-stored value."""
    if isinstance(value, ArrayUnion):
        base = list(existing_value) if isinstance(existing_value, list) else []
        for v in value.values:
            if v not in base:
                base.append(v)
        return base
    return copy.deepcopy(value)


class FakeDocRef:
    def __init__(self, collection: "FakeCollection", doc_id: str):
        self._collection = collection
        self.id = doc_id

    async def get(self) -> FakeDocSnapshot:
        return FakeDocSnapshot(self.id, self._collection._docs.get(self.id))

    async def set(self, data: dict, merge: bool = False) -> None:
        existing = self._collection._docs.get(self.id, {}) if merge else {}
        resolved = {k: _resolve_value(v, existing.get(k)) for k, v in data.items()}
        if merge and self.id in self._collection._docs:
            self._collection._docs[self.id].update(resolved)
        else:
            self._collection._docs[self.id] = resolved

    async def update(self, data: dict) -> None:
        existing = self._collection._docs.setdefault(self.id, {})
        for key, value in data.items():
            resolved = _resolve_value(value, existing.get(key.split(".")[0]) if "." not in key else None)
            if "." in key:
                _set_nested(existing, key, resolved)
            else:
                existing[key] = resolved

    async def delete(self) -> None:
        self._collection._docs.pop(self.id, None)

    def collection(self, name: str) -> "FakeCollection":
        """Subcollection under this document, e.g. leaderboards/{season}/scores."""
        sub = self._collection._subcollections.setdefault(self.id, {})
        return FakeCollection(sub.setdefault(name, {}))


class FakeAggregationResult:
    def __init__(self, value: int):
        self.value = value


class FakeCountQuery:
    def __init__(self, query: "FakeQuery"):
        self._query = query

    async def get(self):
        return [[FakeAggregationResult(len(self._query._filtered_items()))]]


_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "=": lambda a, b: a == b,
}


class FakeQuery:
    """Minimal emulation of a Firestore Query — only what leaderboard.py needs:
    where()/order_by()/limit()/count()/get()."""

    def __init__(self, docs_dict: dict):
        self._docs_dict = docs_dict
        self._filters: list[tuple] = []
        self._order: tuple | None = None
        self._limit_n: int | None = None

    def where(self, field: str, op: str, value) -> "FakeQuery":
        self._filters.append((field, op, value))
        return self

    def order_by(self, field: str, direction: str = "ASCENDING") -> "FakeQuery":
        self._order = (field, direction)
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit_n = n
        return self

    def count(self) -> FakeCountQuery:
        return FakeCountQuery(self)

    def _filtered_items(self) -> list[tuple]:
        items = list(self._docs_dict.items())
        for field, op, value in self._filters:
            fn = _OPS[op]
            items = [(k, v) for k, v in items if fn(v.get(field, 0), value)]
        if self._order:
            field, direction = self._order
            items = sorted(items, key=lambda kv: kv[1].get(field, 0), reverse=(direction == "DESCENDING"))
        if self._limit_n is not None:
            items = items[: self._limit_n]
        return items

    async def get(self):
        return [FakeDocSnapshot(k, v) for k, v in self._filtered_items()]


class FakeCollection:
    def __init__(self, docs: dict):
        self._docs = docs
        self._subcollections: dict[str, dict] = {}

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self, doc_id)

    def where(self, field: str, op: str, value) -> FakeQuery:
        return FakeQuery(self._docs).where(field, op, value)

    def order_by(self, field: str, direction: str = "ASCENDING") -> FakeQuery:
        return FakeQuery(self._docs).order_by(field, direction)

    def count(self) -> FakeCountQuery:
        return FakeCountQuery(FakeQuery(self._docs))

    async def get(self):
        return [FakeDocSnapshot(k, v) for k, v in self._docs.items()]


class FakeFirestoreClient:
    """Duck-typed stand-in for google.cloud.firestore.AsyncClient — only
    implements .collection(name).document(id).{get,set,update,delete}, which is
    all auth_service.py uses."""

    def __init__(self):
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self._collections.setdefault(name, {}))

    def seed(self, collection: str, doc_id: str, data: dict) -> None:
        """Test helper: directly inject a document, bypassing the app."""
        self._collections.setdefault(collection, {})[doc_id] = copy.deepcopy(data)


@pytest.fixture
def fake_db() -> FakeFirestoreClient:
    return FakeFirestoreClient()


# ---------------------------------------------------------------------------
# RSA keypairs — one for the app's own JWT signing, one to play "Apple"
# ---------------------------------------------------------------------------


def _gen_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode()
    return private_key, private_pem


def _b64url_uint(n: int) -> str:
    length = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode("ascii")


def _public_jwk(private_key, kid: str) -> dict:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


@pytest.fixture(scope="session")
def app_signing_key():
    private_key, private_pem = _gen_keypair()
    return private_pem


@pytest.fixture(scope="session")
def apple_signing_key():
    """A (private_key, private_pem, kid, jwk) tuple standing in for one of
    Apple's real JWKS signing keys."""
    private_key, private_pem = _gen_keypair()
    kid = "test-apple-kid-1"
    return {
        "private_key": private_key,
        "private_pem": private_pem,
        "kid": kid,
        "jwk": _public_jwk(private_key, kid),
    }


@pytest.fixture(scope="session")
def apple_signing_key_untrusted():
    """A second keypair whose public JWK is deliberately NOT published — used to
    simulate a forged/tampered token signed by an attacker."""
    private_key, private_pem = _gen_keypair()
    return {"private_key": private_key, "private_pem": private_pem, "kid": "test-apple-kid-1"}


def make_apple_token(
    apple_signing_key: dict,
    *,
    sub: str = "001234.abcdef1234567890.1890",
    aud: str = "com.ingeniouscruciblestudios.motamaze",
    email: str | None = "player@example.com",
    exp_delta: timedelta = timedelta(minutes=5),
    kid: str | None = None,
    signing_pem: str | None = None,
) -> str:
    """Builds a JWT shaped like a real Apple identity_token, signed with the
    given (test) key."""
    from jose import jwt as jose_jwt

    now = datetime.now(timezone.utc)
    claims = {
        "iss": "https://appleid.apple.com",
        "aud": aud,
        "sub": sub,
        "iat": now,
        "exp": now + exp_delta,
    }
    if email is not None:
        claims["email"] = email
        claims["email_verified"] = True

    return jose_jwt.encode(
        claims,
        signing_pem or apple_signing_key["private_pem"],
        algorithm="RS256",
        headers={"kid": kid or apple_signing_key["kid"]},
    )


# ---------------------------------------------------------------------------
# App / client wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        gcp_project_id="motamaze-test",
        environment="test",
        jwt_issuer="https://api.motamaze.test",
        jwt_key_id="test-key-v1",
        jwt_secret_name="jwt-private-key-test",
        google_oauth_client_id="test-google-client-id",
        apple_bundle_id="com.ingeniouscruciblestudios.motamaze",
        apple_environment="Sandbox",
    )


@pytest.fixture(autouse=True)
def _patch_jwt_signing_key(monkeypatch, app_signing_key):
    """Every test gets a fixed, fast, offline RSA key instead of hitting
    Secret Manager — patches the function itself so jwt_service's internal
    TTLCache is never consulted."""
    monkeypatch.setattr(jwt_service, "_get_private_key", lambda project_id, secret_name: app_signing_key)


@pytest.fixture(autouse=True)
def _patch_apple_jwks(monkeypatch, apple_signing_key):
    """By default, Apple's JWKS resolves to a single trusted test key. Individual
    tests can monkeypatch auth_service._get_apple_jwks again to simulate other
    scenarios (empty JWKS, rotated keys, etc.)."""

    async def _fake_jwks():
        return [apple_signing_key["jwk"]]

    monkeypatch.setattr(auth_service, "_get_apple_jwks", _fake_jwks)


@pytest.fixture(autouse=True)
def _patch_bq_streaming(monkeypatch):
    """BackgroundTasks run in-process under the test transport — without this,
    every login/refresh/logout/payments call would attempt a real BigQuery insert."""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.auth.stream_event", _noop)
    monkeypatch.setattr("app.routers.payments.stream_event", _noop)
    monkeypatch.setattr("app.routers.leaderboard.stream_event", _noop)


@pytest.fixture
async def client(fake_db, test_settings):
    app.dependency_overrides[get_firestore_client] = lambda: fake_db
    app.dependency_overrides[get_settings] = lambda: test_settings
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
