# -*- coding: utf-8 -*-
"""课堂管理接口（对应修改报告第 27 节 /api/classrooms/*）。

负责课堂的开始、结束、历史查询与详情统计，
是"课程 -> 课堂 -> 检测记录 -> 专注度记录"业务链路的中间环节。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
from database.database import get_db
from database.models import AttentionRecord, ClassSession, Course, DetectionRecord, User
from routers.auth import get_current_user
from routers.course import get_course_or_404
from schemas.classroom import SessionDetail, SessionOut, SessionStart
from services import report_service

router = APIRouter(prefix="/api/classrooms", tags=["课堂管理"])


def _check_session_permission(session: ClassSession, user: User) -> None:
    if user.role != "admin" and session.course.teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作其他教师的课堂")


def get_session_or_404(db: Session, session_id: int) -> ClassSession:
    session = db.get(ClassSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课堂不存在")
    return session


@router.post("/start", response_model=SessionOut, status_code=status.HTTP_201_CREATED, summary="开始一次课堂")
def start_session(
    payload: SessionStart,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    course = get_course_or_404(db, payload.course_id)
    if user.role != "admin" and course.teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权为该课程创建课堂")

    running = db.execute(
        select(ClassSession).where(
            ClassSession.course_id == course.id, ClassSession.status == "running"
        )
    ).scalars().first()
    if running is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"该课程已有正在进行的课堂（ID {running.id}），请先结束该课堂",
        )

    session = ClassSession(
        course_id=course.id,
        start_time=datetime.now(),
        status="running",
        duration=0,
        created_by=user.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return report_service.session_card(db, session)


@router.post("/{session_id}/stop", response_model=SessionOut, summary="结束课堂")
def stop_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = get_session_or_404(db, session_id)
    _check_session_permission(session, user)

    if session.status != "finished":
        session.end_time = datetime.now()
        if session.start_time:
            session.duration = int((session.end_time - session.start_time).total_seconds())
        session.status = "finished"
        db.commit()
        db.refresh(session)
    return report_service.session_card(db, session)


@router.get("", response_model=list[SessionOut], summary="课堂列表")
def list_sessions(
    course_id: int | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    teacher_id = None if user.role == "admin" else user.id
    rows = report_service.history_sessions(
        db, course_id=course_id, limit=limit, teacher_id=teacher_id
    )
    if status_filter:
        rows = [row for row in rows if row["status"] == status_filter]
    return rows


@router.get("/{session_id}", response_model=SessionDetail, summary="课堂详情")
def get_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = get_session_or_404(db, session_id)
    _check_session_permission(session, user)

    card = report_service.session_card(db, session)
    card.update(
        {
            "behavior_totals": report_service.behavior_totals(db, session.id),
            "attention_series": report_service.attention_series(db, session.id),
            "student_count": card.get("student_count", 0),
            "max_attention": card.get("max_attention"),
            "min_attention": card.get("min_attention"),
        }
    )
    return card


@router.get("/{session_id}/records", summary="课堂检测明细记录")
def session_records(
    session_id: int,
    limit: int = 200,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session = get_session_or_404(db, session_id)
    _check_session_permission(session, user)

    attention_rows = db.execute(
        select(AttentionRecord)
        .where(AttentionRecord.session_id == session_id)
        .order_by(AttentionRecord.record_time.desc())
        .limit(limit)
    ).scalars().all()
    detection_rows = db.execute(
        select(DetectionRecord)
        .where(DetectionRecord.session_id == session_id)
        .order_by(DetectionRecord.detection_time.desc())
        .limit(limit * 3)
    ).scalars().all()

    return {
        "session_id": session_id,
        "attention_records": [
            {
                "id": row.id,
                "record_time": row.record_time.strftime("%H:%M:%S") if row.record_time else "",
                "student_count": row.student_count,
                "focused_count": row.focused_count,
                "unfocused_count": row.unfocused_count,
                "attention_score": round(row.attention_score, 2),
            }
            for row in reversed(attention_rows)
        ],
        "detection_records": [
            {
                "id": row.id,
                "behavior_type": row.behavior_type,
                "behavior_cn": config.behavior_cn(row.behavior_type),
                "person_count": row.person_count,
                "avg_confidence": round(row.avg_confidence, 4),
                "frame_index": row.frame_index,
                "detection_time": row.detection_time.strftime("%H:%M:%S") if row.detection_time else "",
            }
            for row in detection_rows
        ],
    }


@router.delete("/{session_id}", summary="删除课堂记录")
def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = get_session_or_404(db, session_id)
    _check_session_permission(session, user)
    db.delete(session)
    db.commit()
    return {"success": True, "message": "课堂记录已删除"}
