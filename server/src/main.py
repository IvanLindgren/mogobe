import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.auth.router import router as auth_router
from src.auth.service import AttemptLimiter
from src.config import Settings
from src.database import make_engine
from src.legacy.router import router as legacy_router
from src.legacy.socket import router as socket_router
from src.profiles.router import router as social_router
from src.world.hub import WorldHub
from src.world.router import router as world_router

HTTP_LOG = logging.getLogger("mogobe.http")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await engine.dispose()

    app = FastAPI(title="Mogobe server", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.world = WorldHub(settings.server_name)
    app.state.world_players = app.state.world.players
    app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
    app.state.attempt_limiter = AttemptLimiter(settings.login_limit, settings.login_window_seconds)

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        started = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            # Only the decoded route path is logged. Never include URL queries,
            # headers, cookies or request bodies, including on validation errors.
            HTTP_LOG.log(
                logging.ERROR if status >= 500 else logging.INFO,
                "%s %r -> %s (%.1f ms)",
                request.method,
                request.url.path,
                status,
                (perf_counter() - started) * 1000,
            )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic errors otherwise echo the submitted password in their "input".
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.get("/api/health")
    async def health():
        return {"ok": True, "version": "0.1.0"}

    app.include_router(auth_router)
    app.include_router(legacy_router)
    app.include_router(socket_router)
    app.include_router(world_router)
    app.include_router(social_router)
    return app


app = create_app()
