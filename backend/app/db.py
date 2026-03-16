import logging
import ssl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from passlib.hash import bcrypt

from app.config import get_settings

# asyncpg SSL context for Supabase pooler.
# Supabase's *.pooler.supabase.com cert is not standards compliant, so we
# skip cert verification for DB connections only.  OpenAI TLS is fixed
# separately in embeddings.py via a truststore.SSLContext on the httpx client.
_pg_ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_pg_ssl_ctx.check_hostname = False
_pg_ssl_ctx.verify_mode = ssl.CERT_NONE

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def _build_database_url(url: str) -> str:
    """Normalize the DB URL for asyncpg driver and Supabase compatibility."""
    # Convert plain postgres:// or postgresql:// to asyncpg driver scheme
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _use_transaction_pooler(url: str) -> str:
    """Switch Supabase session-mode pooler (port 5432) to transaction-mode (port 6543).

    Transaction mode handles far more concurrent connections because it releases
    the backend PG connection at transaction boundaries rather than holding it
    for the entire client session.
    """
    if "pooler.supabase.com:5432" in url:
        return url.replace(":5432/", ":6543/")
    return url


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        raw_url = settings.supabase_database_url or settings.database_url
        database_url = _build_database_url(raw_url)
        database_url = _use_transaction_pooler(database_url)
        engine_kwargs: dict = {
            "echo": settings.log_level.upper() == "DEBUG",
        }
        if "postgresql" in database_url:
            connect_args: dict = {"ssl": _pg_ssl_ctx}
            # PgBouncer in transaction mode doesn't support prepared statements;
            # disable asyncpg's statement cache to avoid "prepared statement does
            # not exist" errors.
            if "pooler.supabase.com" in database_url:
                connect_args["statement_cache_size"] = 0
                connect_args["prepared_statement_cache_size"] = 0
            engine_kwargs.update({
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_pool_overflow,
                "pool_recycle": settings.db_pool_recycle,
                "pool_pre_ping": True,
                "pool_timeout": 60,
                "connect_args": connect_args,
            })
        _engine = create_async_engine(database_url, **engine_kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncSession:
    """FastAPI dependency for DB sessions."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def seed_admin() -> None:
    """Create default admin user if none exists."""
    from app.models.db_models import AdminUser

    settings = get_settings()
    factory = get_session_factory()

    async with factory() as session:
        result = await session.execute(select(AdminUser).limit(1))
        existing = result.scalars().first()
        if existing is not None:
            logger.info("Admin user already exists, skipping seed")
            return

        admin = AdminUser(
            email=settings.admin_email,
            password_hash=bcrypt.hash(settings.admin_password),
            role="admin",
        )
        session.add(admin)
        await session.commit()
        logger.info("Default admin user created")


async def init_db() -> None:
    """Create all tables, run column migrations, and seed admin. Called on app startup."""
    from app.models.db_models import (  # noqa: F401
        Person,
        PersonSource,
        SearchCache,
        DiscoveryJob,
        PersonVersion,
        AdminUser,
        WebhookEndpoint,
        WebhookDelivery,
        ApiKey,
        ApiUsageLog,
        SavedList,
        PersonListItem,
        PersonNote,
        PersonTag,
        AuditLog,
        PublicShare,
    )

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")

    await _run_column_migrations()
    await seed_admin()


async def _run_column_migrations() -> None:
    """
    Idempotent column additions for existing tables.
    Uses ADD COLUMN IF NOT EXISTS so it's safe to run on every startup.
    Only runs on PostgreSQL (SQLite handles new columns via create_all).
    Non-fatal: any failure is logged and swallowed so startup is never blocked.
    """
    from sqlalchemy import text

    settings = get_settings()
    active_url = settings.supabase_database_url or settings.database_url
    if "postgresql" not in active_url and "postgres" not in active_url:
        return  # SQLite picks up new columns from create_all

    migrations = [
        "ALTER TABLE persons ADD COLUMN IF NOT EXISTS image_url TEXT;",
        "ALTER TABLE person_sources ADD COLUMN IF NOT EXISTS scorer_reason VARCHAR(200);",
    ]

    try:
        engine = get_engine()
        async with engine.begin() as conn:
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                    logger.info(f"Migration applied: {sql.strip()}")
                except Exception as e:
                    logger.warning(f"Migration skipped ({sql.strip()}): {e}")
    except Exception as e:
        logger.warning(f"Column migration step failed (non-fatal): {e}")


async def close_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
