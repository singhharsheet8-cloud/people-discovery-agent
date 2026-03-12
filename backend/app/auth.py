import logging
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from passlib.hash import bcrypt
from sqlalchemy import select
from app.db import get_session_factory
from app.models.db_models import AdminUser
from app.config import get_settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


_auto_generated_key: str | None = None


def _get_secret_key() -> str:
    global _auto_generated_key
    key = get_settings().jwt_secret_key
    if key:
        return key
    if _auto_generated_key:
        return _auto_generated_key
    logger.warning("JWT_SECRET_KEY not set — using auto-generated key (tokens won't survive restarts)")
    _auto_generated_key = secrets.token_urlsafe(48)
    return _auto_generated_key


async def verify_admin(email: str, password: str) -> AdminUser | None:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(AdminUser).where(AdminUser.email == email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user and bcrypt.verify(password, user.password_hash):
            return user
    return None


def create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def create_token_pair(data: dict) -> dict:
    """Create both access and refresh tokens."""
    access_data = data.copy()
    access_data["type"] = "access"
    access_expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_data["exp"] = access_expire
    access_token = jwt.encode(access_data, _get_secret_key(), algorithm=ALGORITHM)

    refresh_data = data.copy()
    refresh_data["type"] = "refresh"
    refresh_expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_data["exp"] = refresh_expire
    refresh_token = jwt.encode(refresh_data, _get_secret_key(), algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "bearer",
    }


def verify_refresh_token(token: str) -> dict | None:
    payload = verify_token(token)
    if payload and payload.get("type") == "refresh":
        return payload
    return None


def verify_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.query_params.get("token")


async def require_admin(request: Request) -> dict:
    """FastAPI dependency — rejects requests without a valid admin JWT."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") == "refresh":
        raise HTTPException(status_code=401, detail="Refresh tokens cannot be used as access tokens")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


async def optional_auth(request: Request) -> dict | None:
    """FastAPI dependency — returns user payload if valid token present, None otherwise."""
    token = _extract_token(request)
    if not token:
        return None
    payload = verify_token(token)
    if payload and payload.get("type") == "refresh":
        return None
    return payload
