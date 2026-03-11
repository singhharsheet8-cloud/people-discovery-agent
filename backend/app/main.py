import os
import ssl


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

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.db import init_db, close_db
from app.api.routes import router
from app.api.webhooks import router as webhooks_router
from app.api.api_keys import router as api_keys_router
from app.api.suggest import router as suggest_router
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
    title="People Discovery Platform",
    description="API-first deep person intelligence platform with 12+ source scrapers",
    version="2.0.0",
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
app.include_router(webhooks_router)
app.include_router(api_keys_router)
app.include_router(suggest_router)
