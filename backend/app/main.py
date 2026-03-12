import json as json_lib
import logging
import os
import ssl
import sys
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

import sentry_sdk

from app.config import get_settings
from app.db import init_db, close_db
from app.api.routes import router
from app.api.webhooks import router as webhooks_router
from app.api.api_keys import router as api_keys_router
from app.api.suggest import router as suggest_router
from app.api.lists_notes import router as lists_notes_router
from app.api.websocket import router as websocket_router
from app.api.integrations import router as integrations_router
from app.middleware import (
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    RequestLoggingMiddleware,
    request_id_var,
)


def _fix_ssl():
    try:
        import truststore
        truststore.inject_into_ssl()
        return
    except Exception:
        pass
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass


_fix_ssl()

settings = get_settings()


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
        }
        rid = request_id_var.get("")
        if rid:
            log_entry["request_id"] = rid
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json_lib.dumps(log_entry)


def setup_logging(level: str):
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers = [handler]


setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from app.cache import cleanup_expired_cache

    await init_db()

    async def _periodic_cache_cleanup():
        while True:
            await asyncio.sleep(600)
            try:
                await cleanup_expired_cache()
            except Exception:
                pass

    cleanup_task = asyncio.create_task(_periodic_cache_cleanup())
    yield
    cleanup_task.cancel()
    await close_db()
    from app.redis_client import close_redis

    await close_redis()


app = FastAPI(
    title="People Discovery Platform",
    description="API-first deep person intelligence platform with 12+ source scrapers",
    version="2.0.0",
    lifespan=lifespan,
)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=settings.environment,
        release=f"people-discovery@{app.version}",
    )


# ── Global Exception Handlers ──────────────────────────────────────

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    rid = request_id_var.get("")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": _status_to_code(exc.status_code),
            "message": exc.detail,
            "request_id": rid,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = request_id_var.get("")
    errors = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err.get("loc", []))
        errors.append({"field": field, "message": err.get("msg", "")})
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": errors,
            "request_id": rid,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = request_id_var.get("")
    logger.error(f"[{rid}] Unhandled exception on {request.method} {request.url.path}: {exc}")
    logger.debug(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": rid,
        },
    )


def _status_to_code(status: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limit_exceeded",
    }.get(status, "error")


# ── Middleware (order matters: last added = first executed) ─────────

cors_kwargs = {
    "allow_origins": settings.cors_origins.split(","),
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
}
if settings.cors_allow_regex:
    cors_kwargs["allow_origin_regex"] = settings.cors_allow_regex

app.add_middleware(CORSMiddleware, **cors_kwargs)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60, ws_per_minute=20)


# ── Routers ────────────────────────────────────────────────────────

app.include_router(router)
app.include_router(webhooks_router)
app.include_router(api_keys_router)
app.include_router(suggest_router)
app.include_router(lists_notes_router)
app.include_router(websocket_router)
app.include_router(integrations_router)
