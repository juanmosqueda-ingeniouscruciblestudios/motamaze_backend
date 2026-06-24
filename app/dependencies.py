from functools import lru_cache

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.cloud import bigquery, firestore
from jose import ExpiredSignatureError, JWTError

from app.config import Settings
from app.services import jwt_service

_bearer = HTTPBearer()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_firestore_client() -> firestore.AsyncClient:
    return firestore.AsyncClient()


def get_bq_client() -> bigquery.Client:
    return bigquery.Client()


async def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: firestore.AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Dependency for JWT-protected endpoints. Returns decoded claims on success."""
    try:
        claims = jwt_service.decode_access_token(
            credentials.credentials,
            settings.gcp_project_id,
            settings.jwt_secret_name,
            settings.jwt_issuer,
        )
    except ExpiredSignatureError:
        raise HTTPException(
            401,
            detail={"error_code": "AUTH_JWT_EXPIRED", "message": "Access token expired"},
        )
    except JWTError:
        raise HTTPException(
            401,
            detail={"error_code": "AUTH_JWT_INVALID", "message": "Invalid access token"},
        )

    jti = claims.get("jti")
    if jti:
        revoked = await db.collection("revoked_jtis").document(jti).get()
        if revoked.exists:
            raise HTTPException(
                401,
                detail={"error_code": "AUTH_JWT_INVALID", "message": "Token has been revoked"},
            )

    return claims
