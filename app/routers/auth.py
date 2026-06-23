from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


# POST /auth/login             — AUTH-001
# POST /auth/refresh           — AUTH-001
# GET  /auth/pending/{state}   — AUTH-001
# POST /auth/google/callback   — AUTH-001
# POST /auth/logout            — AUTH-001
# DELETE /auth/account         — AUTH-003
