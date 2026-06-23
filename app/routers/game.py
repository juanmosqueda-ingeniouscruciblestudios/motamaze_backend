from fastapi import APIRouter

router = APIRouter(tags=["game"])


# GET  /progress                — GAME-001
# POST /progress/level-complete — GAME-001
# GET  /lives                   — GAME-002
# POST /lives/spend             — GAME-002
# POST /lives/grant             — GAME-002
# GET  /store/catalog           — GAME-003
# POST /events/behavior         — DATA-002
# GET  /profile                 — GAME-004
# POST /profile/equip-skin      — GAME-004
