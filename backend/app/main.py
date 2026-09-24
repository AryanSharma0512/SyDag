from fastapi import FastAPI

from app.config import get_settings
from app.routes import router

app = FastAPI(
    title="YieldLens API",
    version=get_settings().version,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.include_router(router)
