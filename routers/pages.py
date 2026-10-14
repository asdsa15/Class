# -*- coding: utf-8 -*-
"""页面路由：渲染 Web 前端页面（对应修改报告第 28 节）。

原 PyQt5 界面全部由 HTML 模板替代，页面通过 JavaScript 调用 /api/* 接口获取数据：

* /login      登录页面
* /dashboard  首页 Dashboard
* /courses    课程管理
* /classroom  课堂检测（图片 / 视频 / 实时摄像头）
* /history    历史课堂
* /report/{id} 课堂分析报告
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
from database.database import get_db
from database.models import User
from routers.auth import user_to_dict
from services.security import decode_token

router = APIRouter(tags=["页面"], include_in_schema=False)
templates = Jinja2Templates(directory=str(config.TEMPLATE_DIR))


def current_user_or_none(request: Request, db: Session) -> User | None:
    """从 Cookie 中解析当前登录用户，失败返回 None。"""
    token = request.cookies.get(config.COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return db.execute(select(User).where(User.username == payload.get("sub"))).scalar_one_or_none()


def _render(request: Request, template: str, user: User, **extra: object) -> HTMLResponse:
    context = {
        "request": request,
        "user": user_to_dict(user),
        "app_name": config.BASE_DIR.name,
        "weights": config.ATTENTION_WEIGHTS,
        "behaviors": [
            {"key": key, "name_cn": config.behavior_cn(key), "name_en": config.behavior_en(key)}
            for key in config.BEHAVIOR_ORDER
        ],
        **extra,
    }
    return templates.TemplateResponse(request, template, context)


def _require_login(request: Request, db: Session) -> User | RedirectResponse:
    user = current_user_or_none(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return user


@router.get("/", include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse(
        url="/dashboard" if current_user_or_none(request, db) else "/login", status_code=302
    )


@router.get("/login", response_class=HTMLResponse, summary="登录页面")
def login_page(request: Request, db: Session = Depends(get_db)):
    if current_user_or_none(request, db):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse, summary="首页 Dashboard")
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return _render(request, "index.html", user, active="dashboard", page_title="首页概览")


@router.get("/courses", response_class=HTMLResponse, summary="课程管理页面")
def course_page(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return _render(request, "course.html", user, active="courses", page_title="课程管理")


@router.get("/classroom", response_class=HTMLResponse, summary="课堂检测页面")
def classroom_page(
    request: Request,
    course_id: int | None = None,
    session_id: int | None = None,
    db: Session = Depends(get_db),
):
    user = _require_login(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return _render(
        request,
        "classroom.html",
        user,
        active="classroom",
        page_title="课堂检测",
        course_id=course_id,
        session_id=session_id,
    )


@router.get("/history", response_class=HTMLResponse, summary="历史课堂页面")
def history_page(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return _render(request, "history.html", user, active="history", page_title="历史课堂")


@router.get("/report/{session_id}", response_class=HTMLResponse, summary="课堂报告页面")
def report_page(request: Request, session_id: int, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return _render(
        request,
        "report.html",
        user,
        active="history",
        page_title="课堂分析报告",
        session_id=session_id,
    )


@router.get("/users", response_class=HTMLResponse, summary="用户管理页面（管理员）")
def users_page(request: Request, db: Session = Depends(get_db)):
    """用户管理页面，仅管理员可访问；教师访问时跳回首页。"""
    user = _require_login(request, db)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)
    return _render(request, "users.html", user, active="users", page_title="用户管理")


@router.get("/profile", response_class=HTMLResponse, summary="个人中心页面")
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return _render(request, "profile.html", user, active="profile", page_title="个人中心")
