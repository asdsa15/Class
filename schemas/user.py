# -*- coding: utf-8 -*-
"""用户与登录相关的数据结构。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

import config


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., min_length=1, max_length=50, description="登录账号")
    password: str = Field(..., min_length=1, max_length=128, description="登录密码")
    remember_me: bool = Field(False, description="记住登录状态（前端仅保存账号，不保存明文密码）")


class UserOut(BaseModel):
    """用户信息（不含密码）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: str = ""
    role: str = "teacher"
    create_time: datetime | None = None
    role_name: str = ""
    status: int = 1
    status_name: str = "正常"
    update_time: datetime | None = None
    last_login_time: datetime | None = None
    course_count: int = 0


class UserCreate(BaseModel):
    """管理员创建用户。"""

    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=128, description="密码至少 6 位")
    real_name: str = Field("", max_length=50)
    role: str = Field("teacher", description="admin 管理员 / teacher 教师")


class UserUpdate(BaseModel):
    """管理员修改用户信息（字段可选）。"""

    real_name: str | None = Field(None, max_length=50)
    role: str | None = Field(None, description="admin 管理员 / teacher 教师")
    status: int | None = Field(None, description="1 正常 / 0 禁用")


class PasswordReset(BaseModel):
    """管理员重置用户密码（原密码由用户自行修改，管理员不可查看）。"""

    new_password: str = Field(..., min_length=6, max_length=128)


class PasswordChange(BaseModel):
    """修改密码。"""

    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class LoginResponse(BaseModel):
    """登录成功的返回结果。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = config.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    remember_me: bool = False
    user: UserOut
