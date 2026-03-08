import os
import ssl

def _fix_ssl():
    """Ensure HTTPS works on any platform (macOS, Linux, Windows).

    macOS Python often ships with outdated OpenSSL and no system certs.
    truststore uses the native OS cert store; certifi is the fallback.
    """
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

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.db import init_db, close_db
from app.api.routes import router
from app.api.websocket import websocket_endpoint
from app.middleware import RateLimitMiddleware, RequestIDMiddleware

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    import asyncio
    from app.cache import cleanup_expired_cache

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


app = FastAPI(
    title="People Discovery Agent",
    description="AI-powered person discovery with multi-source search and confidence scoring",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60, ws_per_minute=20)

app.include_router(router)
app.websocket("/api/ws/{session_id}")(websocket_endpoint)
app.websocket("/api/ws")(websocket_endpoint)
