"""Application factory: `uvicorn quorum.web.app:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from quorum.application.service import QuorumService
from quorum.config import Settings
from quorum.domain.model import (
    DomainError,
    ForbiddenError,
    NotFoundError,
    QuestionsClosedError,
    RateLimitedError,
)
from quorum.infrastructure.database import create_pool, migrate
from quorum.infrastructure.notifications import ChangeHub, PostgresNotifier
from quorum.infrastructure.repository import PostgresRepository
from quorum.web.routes import router
from quorum.web.security import SameOriginMiddleware, SecurityHeadersMiddleware
from quorum.web.templating import WEB_DIR, templates

ERROR_STATUS: dict[type[DomainError], int] = {
    NotFoundError: 404,
    ForbiddenError: 403,
    QuestionsClosedError: 409,
    RateLimitedError: 429,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()  # values come from QUORUM_* environment variables

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = await create_pool(config.database_url)
        await migrate(pool)
        hub = ChangeHub()
        notifier = PostgresNotifier(pool, config.database_url, hub)
        await notifier.start()
        app.state.pool = pool
        app.state.hub = hub
        app.state.service = QuorumService(PostgresRepository(pool), notifier)
        try:
            yield
        finally:
            await notifier.stop()
            await pool.close()

    app = FastAPI(
        title="Quorum", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.secret_key,
        session_cookie="quorum_session",
        same_site="lax",
        https_only=config.secure_cookies,
        max_age=60 * 60 * 24 * 30,
    )
    app.add_middleware(SameOriginMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    app.include_router(router)

    async def domain_error(request: Request, error: Exception) -> Response:
        status = next((code for kind, code in ERROR_STATUS.items() if isinstance(error, kind)), 400)
        context = {"message": str(error), "status": status}
        return templates.TemplateResponse(request, "error.html", context, status_code=status)

    async def invalid_request(request: Request, _error: Exception) -> Response:
        context = {"message": "That link or form wasn't valid.", "status": 400}
        return templates.TemplateResponse(request, "error.html", context, status_code=400)

    async def http_error(request: Request, error: Exception) -> Response:
        status = error.status_code if isinstance(error, HTTPException) else 500
        message = "There's nothing here." if status == 404 else "That didn't work."
        context = {"message": message, "status": status}
        return templates.TemplateResponse(request, "error.html", context, status_code=status)

    app.add_exception_handler(DomainError, domain_error)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(HTTPException, http_error)
    return app
