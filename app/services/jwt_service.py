import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from cachetools import TTLCache
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
)
from google.cloud import secretmanager
from jose import jwt

# Private key cached for 5 min — avoids Secret Manager round-trip on every request.
_key_cache: TTLCache = TTLCache(maxsize=2, ttl=300)


def _get_private_key(project_id: str, secret_name: str) -> str:
    cache_key = f"{project_id}/{secret_name}/private"
    cached = _key_cache.get(cache_key)
    if cached:
        return cached
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    pem = response.payload.data.decode("utf-8")
    _key_cache[cache_key] = pem
    return pem


def get_public_key_pem(project_id: str, secret_name: str) -> str:
    cache_key = f"{project_id}/{secret_name}/public"
    cached = _key_cache.get(cache_key)
    if cached:
        return cached
    private_pem = _get_private_key(project_id, secret_name)
    private_key_obj = load_pem_private_key(private_pem.encode(), password=None)
    pub_pem = private_key_obj.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode()
    _key_cache[cache_key] = pub_pem
    return pub_pem


def create_access_token(
    user_id: str,
    provider: str,
    session_id: str,
    project_id: str,
    secret_name: str,
    key_id: str,
    issuer: str,
) -> tuple[str, str]:
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer,
        "sub": user_id,
        "aud": "motamaze-api",
        "exp": now + timedelta(seconds=900),
        "iat": now,
        "jti": jti,
        "uid": user_id,
        "provider": provider,
        "sid": session_id,
    }
    private_key = _get_private_key(project_id, secret_name)
    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": key_id})
    return token, jti


def decode_access_token(
    token: str,
    project_id: str,
    secret_name: str,
    issuer: str,
) -> dict:
    """Verifies signature, aud, iss, exp. Raises jose.JWTError on failure."""
    public_key = get_public_key_pem(project_id, secret_name)
    return jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience="motamaze-api",
        issuer=issuer,
        options={"leeway": 30},
    )


def create_refresh_token(session_id: str) -> str:
    """Returns '{session_id}.{random_secret}' — prefix enables O(1) session lookup."""
    return f"{session_id}.{uuid.uuid4()}"


def extract_session_and_secret(refresh_token: str) -> tuple[str, str]:
    parts = refresh_token.split(".", 1)
    if len(parts) != 2:
        raise ValueError("Invalid refresh token format")
    return parts[0], parts[1]


def hash_refresh_token(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_refresh_token(secret: str, token_hash: str) -> bool:
    return bcrypt.checkpw(secret.encode(), token_hash.encode())
