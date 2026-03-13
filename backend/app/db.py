import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from passlib.hash import bcrypt

from app.config import get_settings

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


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        database_url = _build_database_url(settings.database_url)
        engine_kwargs: dict = {
            "echo": settings.log_level.upper() == "DEBUG",
        }
        if "postgresql" in database_url:
            # Supabase requires SSL; pass via connect_args for asyncpg
            import ssl as ssl_module
            ssl_ctx = ssl_module.create_default_context()
            engine_kwargs.update({
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_pool_overflow,
                "pool_recycle": settings.db_pool_recycle,
                "pool_pre_ping": True,
                "pool_timeout": 30,
                "connect_args": {"ssl": ssl_ctx},
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
    """Create all tables and seed admin. Called on app startup."""
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

    await seed_admin()


async def close_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
