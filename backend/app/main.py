"""SubseaSim FastAPI application.

EDUCATIONAL SIMULATOR ONLY. This service has no drivers, protocols or
network clients for any real control system (SCADA, DCS, subsea control
modules, OPC, Modbus, ...). It must never be connected to one.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router, ws_router
from app.core.config import settings
from app.core.model_registry import APP_VERSION
from app.storage.records import StorageUnavailable
from app.sessions import manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    manager.start()
    yield
    await manager.stop()


app = FastAPI(
    title="SubseaSim",
    description="Educational subsea production simulator. All values are SIMULATED.",
    version=APP_VERSION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(ws_router)


@app.exception_handler(StorageUnavailable)
async def _storage_unavailable(_: Request, exc: StorageUnavailable) -> JSONResponse:
    # e.g. a root-owned volume while the server runs as a non-root user: say what to fix
    return JSONResponse(status_code=503, content={"detail": f"Records storage unavailable: {exc}. Mount a writable volume at the "
                                                            "SUBSEASIM_DB_PATH folder (Railway: also set RAILWAY_RUN_UID=0)."})

# Production: serve the built frontend from the same origin.
if settings.frontend_dist and Path(settings.frontend_dist).is_dir():
    dist = Path(settings.frontend_dist)
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = dist / path
        if path and candidate.is_file() and dist in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
