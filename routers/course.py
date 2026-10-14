# -*- coding: utf-8 -*-
"""课程管理接口（对应修改报告第 27 节 /api/courses/*）。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import AttentionRecord, ClassSession, Course, User
from routers.auth import get_current_user
from schemas.course import CourseCreate, CourseOut, CourseUpdate

router = APIRouter(prefix="/api/courses", tags=["课程管理"])


def course_payload(db: Session, course: Course) -> dict[str, Any]:
    """课程对象 -> 前端需要的结构（附带课堂数量与平均专注度）。"""
    session_count = int(
        db.execute(
            select(func.count(ClassSession.id)).where(ClassSession.course_id == course.id)
        ).scalar()
        or 0
    )
    avg_attention = db.execute(
        select(func.avg(AttentionRecord.attention_score))
        .join(ClassSession, ClassSession.id == AttentionRecord.session_id)
        .where(ClassSession.course_id == course.id)
    ).scalar()
    teacher = course.teacher
    return {
        "id": course.id,
        "course_name": course.course_name,
        "teacher_id": course.teacher_id,
        "teacher_name": (getattr(teacher, "real_name", "") or getattr(teacher, "username", "")),
        "class_name": course.class_name or "",
        "classroom": course.classroom or "",
        "description": course.description or "",
        "create_time": course.create_time,
        "session_count": session_count,
        "avg_attention": round(float(avg_attention), 2) if avg_attention is not None else None,
    }


def get_course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程不存在")
    return course


def _check_permission(course: Course, user: User) -> None:
    """教师只能操作自己的课程，管理员可以操作全部课程。"""
    if user.role != "admin" and course.teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作其他教师的课程")


@router.get("", response_model=list[CourseOut], summary="课程列表")
def list_courses(
    keyword: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    statement = select(Course).order_by(Course.id.desc())
    if user.role != "admin":
        statement = statement.where(Course.teacher_id == user.id)
    if keyword:
        statement = statement.where(Course.course_name.like(f"%{keyword}%"))
    courses = db.execute(statement).scalars().all()
    return [course_payload(db, course) for course in courses]


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED, summary="新建课程")
def create_course(
    payload: CourseCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    teacher_id = payload.teacher_id or user.id
    if user.role != "admin" and teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有管理员可以指定授课教师")
    if db.get(User, teacher_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="指定的授课教师不存在")

    course = Course(
        course_name=payload.course_name,
        teacher_id=teacher_id,
        class_name=payload.class_name,
        classroom=payload.classroom,
        description=payload.description,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course_payload(db, course)


@router.get("/{course_id}", response_model=CourseOut, summary="课程详情")
def get_course(
    course_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    course = get_course_or_404(db, course_id)
    _check_permission(course, user)
    return course_payload(db, course)


@router.put("/{course_id}", response_model=CourseOut, summary="修改课程")
def update_course(
    course_id: int,
    payload: CourseUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    course = get_course_or_404(db, course_id)
    _check_permission(course, user)

    data = payload.model_dump(exclude_unset=True)
    if "teacher_id" in data and data["teacher_id"] is not None:
        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有管理员可以更换授课教师")
        if db.get(User, data["teacher_id"]) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="指定的授课教师不存在")

    for field, value in data.items():
        if value is not None:
            setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course_payload(db, course)


@router.delete("/{course_id}", summary="删除课程")
def delete_course(
    course_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    course = get_course_or_404(db, course_id)
    _check_permission(course, user)
    db.delete(course)
    db.commit()
    return {"success": True, "message": "课程及其课堂记录已删除"}
