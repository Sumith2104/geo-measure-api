import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import router
from app.config import settings
from app.db import Base, engine

log = logging.getLogger("geo")


def create_app() -> FastAPI:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    app = FastAPI(title="Geospatial File Measurement API", version="1.0.0")
    app.include_router(router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "INTERNAL_ERROR", "message": "Unexpected error"}},
        )

    return app


app = create_app()
