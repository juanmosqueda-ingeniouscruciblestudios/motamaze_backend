import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from cachetools import TTLCache
from google.cloud import secretmanager
from jose import jwt

# Private key cached for 5 min — avoids Secret Manager round-trip on every request.
# maxsize=1: we only ever cache one key (the current active version).
_key_cache: TTLCache = TTLCache(maxsize=1, ttl=300)


def _get_private_key(project_id: str, secret_name: str) -> str:
    cache_key = f"{project_id}/{secret_name}"
    cached = _key_cache.get(cache_key)
    if cached:
        return cached
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    pem = response.payload.data.decode("utf-8")
    _key_cache[cache_key] = pem
    return pem


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


def create_refresh_token() -> str:
    return str(uuid.uuid4())


def hash_refresh_token(token: str) -> str:
    return bcrypt.hashpw(token.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_refresh_token(token: str, token_hash: str) -> bool:
    return bcrypt.checkpw(token.encode(), token_hash.encode())
