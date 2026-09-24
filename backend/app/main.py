from fastapi import FastAPI

from app.config import get_settings
from app.context_routes import router as context_router
from app.routes import router

app = FastAPI(
    title="SoilSignal API",
    version=get_settings().version,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.include_router(router)
app.include_router(context_router)
