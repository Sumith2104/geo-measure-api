import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.api import router
from app.config import settings
from app.db import Base, engine

log = logging.getLogger("geo")


def create_app() -> FastAPI:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    app = FastAPI(title="Geospatial File Measurement API", version="1.0.0")
    app.include_router(router)

    template_path = Path(__file__).parent / "templates" / "viewer.html"

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/viewer")

    @app.get("/viewer", response_class=HTMLResponse, tags=["ui"], summary="Interactive Geospatial Map Explorer")
    def viewer():
        return template_path.read_text(encoding="utf-8")

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "INTERNAL_ERROR", "message": "Unexpected error"}},
        )

    return app


app = create_app()
