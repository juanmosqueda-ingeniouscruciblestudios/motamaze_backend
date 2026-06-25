import asyncio

from fastapi import APIRouter, Depends
from jose import jwk as jose_jwk

from app.config import Settings
from app.dependencies import get_settings
from app.services import jwt_service

router = APIRouter(tags=["Discovery"])


@router.get("/.well-known/jwks.json")
async def jwks(settings: Settings = Depends(get_settings)):
    pub_pem = await asyncio.to_thread(
        jwt_service.get_public_key_pem,
        settings.gcp_project_id,
        settings.jwt_secret_name,
    )
    key = jose_jwk.construct(pub_pem, algorithm="RS256")
    public_jwk = key.public_key().to_dict()
    public_jwk["kid"] = settings.jwt_key_id
    public_jwk["use"] = "sig"
    public_jwk["alg"] = "RS256"
    return {"keys": [public_jwk]}
