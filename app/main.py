from fastapi import FastAPI

from app.routers import auth, game, health, jobs, payments, social, well_known

app = FastAPI(title="MotaMaze Backend", version="0.1.0")

app.include_router(health.router)
app.include_router(well_known.router)
app.include_router(auth.router)
app.include_router(game.router)
app.include_router(payments.router)
app.include_router(social.router)
app.include_router(jobs.router)
