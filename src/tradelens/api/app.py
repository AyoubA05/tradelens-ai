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

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.tradelens.api.config import is_production, validate_api_runtime
from src.tradelens.api.routers import overview, session, trades


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
