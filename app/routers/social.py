from fastapi import APIRouter

router = APIRouter(tags=["social"])


# GET  /leaderboard             — T-443
# POST /leaderboard/score       — T-443
# GET  /season                  — Social-001
# POST /season/claim-reward     — Social-001
# GET  /achievements            — Social-002
# POST /share/create            — T-440
# GET  /s/{token}               — T-440 (returns HTML, not JSON)
