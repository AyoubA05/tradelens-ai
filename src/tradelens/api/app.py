"""The FastAPI application.

Public HTTPS, and deliberately not browser-consumed. There is no CORS
middleware: its absence is what makes a browser unable to call this service
cross-origin with credentials, and a test asserts no Access-Control header is
ever emitted. Adding one would be the first step toward this becoming a public
API by accident.

The schema is not served in production. It is generated in CI for TypeScript
codegen, which needs a file rather than a public endpoint.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.tradelens.api.config import is_production, validate_api_runtime
from src.tradelens.api.routers import overview, session, trades
from src.tradelens.api.serialization import to_jsonable


def create_app() -> FastAPI:
    production = is_production()
    validate_api_runtime()
    app = FastAPI(
        title="TradeLens API",
        version="0.1.0",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        # Pydantic correctly rejects a JSON number such as ``1e400`` as
        # infinity, but its error record includes that original value. The
        # default Starlette renderer then raises while serializing the error,
        # converting a safe 422 into a 500. Scrub non-finite diagnostic input
        # using the same strict serializer as successful API payloads.
        return JSONResponse(
            status_code=422,
            content={"detail": to_jsonable(jsonable_encoder(exc.errors()))},
        )

    @app.middleware("http")
    async def no_store(request, call_next):
        """Authenticated responses must not be cached anywhere.

        /health is excluded so a load balancer may cache liveness.
        """
        response = await call_next(request)
        if request.url.path != "/health":
            response.headers["Cache-Control"] = "no-store, private"
        return response

    @app.get("/health")
    def health() -> JSONResponse:
        """Liveness only. Reveals nothing about configuration, data, or version."""
        return JSONResponse({"status": "ok"})

    app.include_router(session.router)
    app.include_router(overview.router)
    app.include_router(trades.router)
    return app


app = create_app()
