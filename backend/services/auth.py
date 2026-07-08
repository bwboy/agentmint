"""Authentication & verification-code services.

- SMS codes live in Redis under `sms:{phone}` (TTL 5 min), survives multi-process.
- JWT signing/verification uses HS256.
- Runtime node tokens are bcrypt-hashed before storage.
"""
import random
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from passlib.context import CryptContext

from config import settings
from services.redis_client import get_redis

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

CODE_TTL_SECONDS = 300


# ─── SMS verification codes ───

async def issue_code(phone: str) -> str:
    """Generate a 6-digit code and store it in Redis.

    For the `mock` provider used in dev, always returns 123456 to make local
    testing painless. Real provider would call Aliyun SMS here.
    """
    if settings.sms_provider == "mock":
        code = "123456"
    else:
        code = f"{random.randint(0, 999999):06d}"
        # TODO: integrate Aliyun dysmsapi when SMS_PROVIDER=aliyun
    redis = get_redis()
    await redis.set(f"sms:{phone}", code, ex=CODE_TTL_SECONDS)
    return code


async def verify_code(phone: str, code: str) -> bool:
    """Verify and consume a one-time code."""
    redis = get_redis()
    key = f"sms:{phone}"
    stored = await redis.get(key)
    if stored is None or stored != code:
        return False
    await redis.delete(key)
    return True


# ─── JWT ───

def create_token(user_id: str, nickname: str, trust_level: int) -> str:
    payload = {
        "sub": user_id,
        "nickname": nickname,
        "trust_level": trust_level,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expiry_hours),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=settings.jwt_refresh_expiry_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None


# ─── Runtime node token hashing ───

def hash_token(token: str) -> str:
    return pwd_context.hash(token)


def verify_token_hash(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ─── FastAPI dependency ───

def get_current_user(request: Request) -> dict:
    """Extract JWT from Authorization header. Raises 401 on failure."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = auth[len("Bearer "):]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="登录已过期")
    return payload
