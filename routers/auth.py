# -*- coding: utf-8 -*-
"""用户认证与权限管理接口（对应 /api/auth/*）。

功能：

* 登录（支持"记住密码"，实现为记住登录状态，浏览器端不保存明文密码）
* 退出登录、获取当前用户、修改密码、个人中心
* 用户管理（管理员）：列表、创建、修改（姓名/角色/状态）、重置密码、删除/禁用
* 登录失败次数限制、账号禁用校验

登录成功后同时返回 JWT 令牌并写入 HttpOnly Cookie：

* 浏览器页面（Jinja2 模板）依赖 Cookie 自动携带登录状态；
* 其他客户端（测试脚本、Postman）可以使用 Authorization: Bearer <token>。
"""

from __future__ import annotations

import string
import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import config
from database.database import get_db
from database.models import Course, User
from schemas.user import (
    LoginRequest,
    LoginResponse,
    PasswordChange,
    PasswordReset,
    UserCreate,
    UserOut,
    UserUpdate,
)
from services.security import create_access_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["用户认证"])
bearer_scheme = HTTPBearer(auto_error=False)

# 登录失败计数（内存实现，服务重启后清空；同一账号连续失败达到上限即临时锁定）
_FAILED_ATTEMPTS: dict[str, list] = {}


def _check_password_strength(password: str) -> None:
    """密码复杂度校验：6~64 位，且至少包含字母、数字、符号中的两类。"""
    if not 6 <= len(password) <= 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码长度需为 6~64 位")
    classes = 0
    if any(ch.isalpha() for ch in password):
        classes += 1
    if any(ch.isdigit() for ch in password):
        classes += 1
    if any(ch in string.punctuation for ch in password):
        classes += 1
    if classes < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码需至少包含字母、数字、符号中的两类",
        )


def _login_locked(username: str) -> int:
    """返回账号剩余锁定秒数（未锁定返回 0）。"""
    record = _FAILED_ATTEMPTS.get(username)
    if not record:
        return 0
    count, locked_until = record
    if count < config.LOGIN_MAX_ATTEMPTS:
        return 0
    remaining = int(locked_until - time.time())
    if remaining > 0:
        return remaining
    # 锁定期已结束，重新开始计数
    _FAILED_ATTEMPTS.pop(username, None)
    return 0


def _record_failure(username: str) -> None:
    count, _ = _FAILED_ATTEMPTS.get(username, [0, 0.0])
    count += 1
    locked_until = time.time() + config.LOGIN_LOCK_SECONDS if count >= config.LOGIN_MAX_ATTEMPTS else 0.0
    _FAILED_ATTEMPTS[username] = [count, locked_until]


def user_to_dict(user: User, course_count: int | None = None) -> dict:
    """用户对象 -> 前端需要的字段（不含密码）。"""
    data = {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name or "",
        "role": user.role,
        "role_name": config.ROLES.get(user.role, user.role),
        "status": int(user.status if user.status is not None else 1),
        "status_name": user.status_name,
        "create_time": user.create_time,
        "update_time": user.update_time,
        "last_login_time": user.last_login_time,
        "course_count": int(course_count or 0),
    }
    return data


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """从 Cookie 或 Authorization 头解析当前登录用户。"""
    token = credentials.credentials if credentials and credentials.credentials else None
    if not token:
        token = request.cookies.get(config.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录状态已失效")

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")

    user = db.execute(select(User).where(User.username == payload.get("sub"))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在或已被删除")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用，请联系管理员")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """要求管理员权限。"""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该操作需要管理员权限")
    return user


@router.post("/login", response_model=LoginResponse, summary="用户登录")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    locked = _login_locked(payload.username)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录失败次数过多，请 {locked} 秒后重试",
        )

    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password):
        _record_failure(payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用，请联系管理员")

    _FAILED_ATTEMPTS.pop(payload.username, None)
    minutes = config.REMEMBER_ME_EXPIRE_MINUTES if payload.remember_me else config.ACCESS_TOKEN_EXPIRE_MINUTES
    token, expires_in = create_access_token(
        user.username, user.role, user.id, expires_minutes=minutes
    )

    user.last_login_time = datetime.now()
    db.commit()
    db.refresh(user)

    response.set_cookie(
        key=config.COOKIE_NAME,
        value=token,
        max_age=expires_in if payload.remember_me else None,  # 未勾选时为会话 Cookie
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "remember_me": payload.remember_me,
        "user": user_to_dict(user),
    }


@router.post("/logout", summary="退出登录")
def logout(response: Response) -> dict:
    response.delete_cookie(config.COOKIE_NAME, path="/")
    return {"success": True, "message": "已退出登录"}


@router.get("/me", response_model=UserOut, summary="获取当前登录用户")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return user_to_dict(user)


@router.put("/me", response_model=UserOut, summary="修改当前用户资料")
def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """普通用户只能修改自己的姓名，角色与状态由管理员维护。"""
    if payload.real_name is not None:
        user.real_name = payload.real_name
    user.update_time = datetime.now()
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@router.post("/password", summary="修改当前账号密码")
def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.old_password, user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
    _check_password_strength(payload.new_password)
    user.password = hash_password(payload.new_password)
    user.update_time = datetime.now()
    db.commit()
    return {"success": True, "message": "密码修改成功，请重新登录"}


@router.get("/users", response_model=list[UserOut], summary="用户列表（管理员）")
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    counts = dict(
        db.execute(
            select(Course.teacher_id, func.count(Course.id)).group_by(Course.teacher_id)
        ).all()
    )
    return [user_to_dict(item, counts.get(item.id, 0)) for item in users]


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建用户（管理员）",
)
def create_user(
    payload: UserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if payload.role not in config.ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色只能是 admin 或 teacher")
    _check_password_strength(payload.password)
    exists = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该账号已存在")

    user = User(
        username=payload.username,
        password=hash_password(payload.password),
        real_name=payload.real_name,
        role=payload.role,
        status=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_dict(user, 0)


@router.put("/users/{user_id}", response_model=UserOut, summary="修改用户（管理员）")
def update_user(
    user_id: int,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if payload.role is not None:
        if payload.role not in config.ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色只能是 admin 或 teacher")
        if user.id == admin.id and payload.role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能取消当前登录账号的管理员角色")
        user.role = payload.role
    if payload.status is not None:
        if payload.status not in (0, 1):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="状态只能是 1 正常 / 0 禁用")
        if user.id == admin.id and payload.status == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前登录账号")
        user.status = payload.status
    if payload.real_name is not None:
        user.real_name = payload.real_name

    user.update_time = datetime.now()
    db.commit()
    db.refresh(user)
    count = db.execute(
        select(func.count(Course.id)).where(Course.teacher_id == user.id)
    ).scalar()
    return user_to_dict(user, count)


@router.post("/users/{user_id}/reset-password", summary="重置用户密码（管理员）")
def reset_password(
    user_id: int,
    payload: PasswordReset,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """管理员重置密码：只能设置新密码，不能查看原密码。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    _check_password_strength(payload.new_password)
    user.password = hash_password(payload.new_password)
    user.update_time = datetime.now()
    db.commit()
    return {"success": True, "message": f"已重置账号 {user.username} 的密码"}


@router.delete("/users/{user_id}", summary="删除用户（管理员）")
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录账号")

    course_count = int(
        db.execute(select(func.count(Course.id)).where(Course.teacher_id == user.id)).scalar() or 0
    )
    if course_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"该教师名下还有 {course_count} 门课程，删除会一并删除其课堂记录。"
                "为保留历史数据，建议改为「禁用」该账号。"
            ),
        )
    db.delete(user)
    db.commit()
    return {"success": True, "message": "用户已删除"}
