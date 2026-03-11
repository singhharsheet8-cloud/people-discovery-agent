import logging
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from passlib.hash import bcrypt
from sqlalchemy import select
from app.db import get_session_factory
from app.models.db_models import AdminUser
from app.config import get_settings

logger = logging.getLogger(__name__)

SECRET_KEY = "discovery-platform-secret-key-change-in-production"
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


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
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
