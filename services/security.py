# -*- coding: utf-8 -*-
"""密码哈希与登录令牌工具。

密码哈希使用标准库 hashlib 实现的 PBKDF2-SHA256（等价于 passlib 的
pbkdf2_sha256 方案），好处是不依赖第三方加密后端，避免 passlib / bcrypt
与高版本 Python 的兼容问题；登录令牌使用 python-jose 生成 JWT。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import config

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """生成密码哈希，格式：pbkdf2_sha256$迭代次数$盐$哈希值。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "$".join(
        [
            _ALGORITHM,
            str(_ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, hashed: str) -> bool:
    """校验密码是否与哈希匹配。"""
    if not hashed:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = hashed.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(
    subject: str,
    role: str = "teacher",
    user_id: int | None = None,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    """生成 JWT 访问令牌，返回 (token, 有效期秒数)。"""
    from jose import jwt

    minutes = int(config.ACCESS_TOKEN_EXPIRE_MINUTES if expires_minutes is None else expires_minutes)
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "uid": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, config.SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    return token, minutes * 60


def decode_token(token: str) -> dict[str, Any] | None:
    """解析 JWT，令牌无效或过期时返回 None。"""
    from jose import JWTError, jwt

    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except JWTError:
        return None
    except Exception:
        return None
