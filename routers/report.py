# -*- coding: utf-8 -*-
"""统计报告接口（对应修改报告第 27 节 /api/reports/*）。

* GET /api/reports/dashboard                 首页仪表盘统计
* GET /api/reports/{session_id}              课堂分析报告
* GET /api/reports/{session_id}/statistics   图表统计数据
* GET /api/reports/courses/{course_id}/compare  同一课程多次课堂对比
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import ClassSession, User
from routers.auth import get_current_user
from routers.classroom import get_session_or_404
from routers.course import get_course_or_404
from schemas.report import DashboardOverview, ReportOverview, ReportStatistics
from services import report_service

router = APIRouter(prefix="/api/reports", tags=["统计报告"])


def _check_session_permission(session: ClassSession, user: User) -> None:
    if user.role != "admin" and session.course.teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看其他教师的课堂报告")


@router.get("/dashboard", response_model=DashboardOverview, summary="首页仪表盘统计")
def dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return report_service.dashboard_overview(db, user)


@router.get("/courses/{course_id}/compare", summary="同一课程多次课堂对比")
def compare_course_sessions(
    course_id: int,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    course = get_course_or_404(db, course_id)
    if user.role != "admin" and course.teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看其他教师的课程")

    rows = report_service.history_sessions(db, course_id=course_id, limit=limit)
    rows = [row for row in rows if row["avg_attention"] is not None]
    rows.reverse()
    return {
        "course_id": course_id,
        "course_name": course.course_name,
        "sessions": rows,
        "labels": [row["date"] for row in rows],
        "values": [row["avg_attention"] for row in rows],
        "avg_attention": (
            round(sum(row["avg_attention"] for row in rows) / len(rows), 2) if rows else None
        ),
    }


@router.get("/{session_id}", response_model=ReportOverview, summary="课堂分析报告")
def session_report(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = get_session_or_404(db, session_id)
    _check_session_permission(session, user)
    report = report_service.session_report(db, session)
    return report


@router.get("/{session_id}/statistics", response_model=ReportStatistics, summary="课堂图表统计数据")
def session_statistics(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = get_session_or_404(db, session_id)
    _check_session_permission(session, user)
    return report_service.session_statistics(db, session)
