# -*- coding: utf-8 -*-
"""统计分析与课堂报告服务（对应修改报告第 22、23、24 节）。

负责把数据库中的行为检测记录、专注度记录汇总为：

* 历史课堂列表（课程 / 日期 / 时长 / 平均专注度）
* 课堂报告（平均、最高、最低专注度 + 行为统计 + 课堂总结）
* 图表数据（专注度趋势、行为柱状图、行为比例、专注度区间分布）
* 首页仪表盘统计
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import config
from database.models import AttentionRecord, ClassSession, Course, DetectionRecord, User
from detection.attention import aggregate_scores, attention_level, bucket_distribution


def _duration_seconds(session: ClassSession) -> int:
    if session.duration:
        return int(session.duration)
    if session.end_time and session.start_time:
        return int((session.end_time - session.start_time).total_seconds())
    if session.start_time:
        return int((datetime.now() - session.start_time).total_seconds())
    return 0


def attention_scores(db: Session, session_id: int) -> list[float]:
    """某次课堂的全部专注度采样值（按时间升序）。"""
    rows = db.execute(
        select(AttentionRecord.attention_score)
        .where(AttentionRecord.session_id == session_id)
        .order_by(AttentionRecord.record_time)
    ).scalars().all()
    return [float(value) for value in rows]


def attention_series(db: Session, session_id: int) -> list[dict[str, Any]]:
    """专注度时间序列（折线图数据）。"""
    rows = db.execute(
        select(
            AttentionRecord.record_time,
            AttentionRecord.attention_score,
            AttentionRecord.student_count,
            AttentionRecord.focused_count,
            AttentionRecord.unfocused_count,
        )
        .where(AttentionRecord.session_id == session_id)
        .order_by(AttentionRecord.record_time)
    ).all()
    return [
        {
            "time": row[0].strftime("%H:%M:%S") if row[0] else "",
            "datetime": row[0].isoformat() if row[0] else "",
            "score": round(float(row[1]), 2),
            "student_count": int(row[2] or 0),
            "focused_count": int(row[3] or 0),
            "unfocused_count": int(row[4] or 0),
        }
        for row in rows
    ]


def behavior_totals(db: Session, session_id: int) -> dict[str, int]:
    """行为统计总量（各行为累计人次，对应报告中的行为统计数据）。"""
    rows = db.execute(
        select(
            DetectionRecord.behavior_type,
            func.sum(DetectionRecord.person_count),
        )
        .where(DetectionRecord.session_id == session_id)
        .group_by(DetectionRecord.behavior_type)
    ).all()
    totals = {key: 0 for key in config.BEHAVIOR_ORDER}
    for behavior_type, total in rows:
        totals[str(behavior_type)] = int(total or 0)
    return totals


def behavior_confidence(db: Session, session_id: int) -> dict[str, float]:
    """各类行为的平均检测置信度（加权平均）。"""
    rows = db.execute(
        select(
            DetectionRecord.behavior_type,
            func.sum(DetectionRecord.person_count),
            func.sum(DetectionRecord.person_count * DetectionRecord.avg_confidence),
        )
        .where(DetectionRecord.session_id == session_id)
        .group_by(DetectionRecord.behavior_type)
    ).all()
    result: dict[str, float] = {}
    for behavior_type, count, weighted in rows:
        count = int(count or 0)
        result[str(behavior_type)] = round(float(weighted or 0) / count, 4) if count else 0.0
    return result


def behavior_series(db: Session, session_id: int) -> list[dict[str, Any]]:
    """行为柱状图 / 饼图数据。"""
    totals = behavior_totals(db, session_id)
    confidences = behavior_confidence(db, session_id)
    total = sum(totals.values()) or 1
    return [
        {
            "key": key,
            "name_cn": config.behavior_cn(key),
            "name_en": config.behavior_en(key),
            "count": totals.get(key, 0),
            "ratio": round(totals.get(key, 0) / total * 100, 2),
            "avg_confidence": confidences.get(key, 0.0),
            "weight": config.ATTENTION_WEIGHTS.get(key, 0.0),
            "focused": key in config.FOCUSED_BEHAVIORS,
        }
        for key in config.BEHAVIOR_ORDER
    ]


def session_card(db: Session, session: ClassSession) -> dict[str, Any]:
    """课堂列表中的一行数据。"""
    row = db.execute(
        select(
            func.avg(AttentionRecord.attention_score),
            func.max(AttentionRecord.attention_score),
            func.min(AttentionRecord.attention_score),
            func.count(AttentionRecord.id),
            func.max(AttentionRecord.student_count),
        ).where(AttentionRecord.session_id == session.id)
    ).one()
    average = round(float(row[0]), 2) if row[0] is not None else None
    course = session.course
    return {
        "id": session.id,
        "course_id": session.course_id,
        "course_name": getattr(course, "course_name", ""),
        "class_name": getattr(course, "class_name", ""),
        "classroom": getattr(course, "classroom", ""),
        "teacher_name": getattr(getattr(course, "teacher", None), "real_name", "")
        or getattr(getattr(course, "teacher", None), "username", ""),
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "date": session.start_time.strftime("%Y-%m-%d") if session.start_time else "",
        "time_range": (
            f"{session.start_time.strftime('%H:%M')} - {session.end_time.strftime('%H:%M')}"
            if session.start_time and session.end_time
            else (session.start_time.strftime("%H:%M") if session.start_time else "")
        ),
        "duration": _duration_seconds(session),
        "duration_minutes": round(_duration_seconds(session) / 60, 1),
        "status": session.status,
        "avg_attention": average,
        "max_attention": round(float(row[1]), 2) if row[1] is not None else None,
        "min_attention": round(float(row[2]), 2) if row[2] is not None else None,
        "record_count": int(row[3] or 0),
        "student_count": int(row[4] or 0),
        "level": attention_level(average),
    }


def history_sessions(
    db: Session,
    course_id: int | None = None,
    limit: int = 200,
    keyword: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    teacher_id: int | None = None,
) -> list[dict[str, Any]]:
    """历史课堂列表（按开始时间倒序）。"""
    statement = (
        select(ClassSession)
        .join(Course, Course.id == ClassSession.course_id)
        .order_by(ClassSession.start_time.desc())
        .limit(limit)
    )
    if course_id:
        statement = statement.where(ClassSession.course_id == course_id)
    if teacher_id is not None:
        statement = statement.where(Course.teacher_id == teacher_id)
    if keyword:
        statement = statement.where(Course.course_name.like(f"%{keyword}%"))
    if start_date:
        statement = statement.where(ClassSession.start_time >= datetime.combine(start_date, time.min))
    if end_date:
        statement = statement.where(ClassSession.start_time <= datetime.combine(end_date, time.max))

    sessions = db.execute(statement).scalars().all()
    return [session_card(db, session) for session in sessions]


def session_report(db: Session, session: ClassSession) -> dict[str, Any]:
    """生成课堂分析报告（对应修改报告第 24 节的课堂报告）。"""
    scores = attention_scores(db, session.id)
    aggregates = aggregate_scores(scores)
    totals = behavior_totals(db, session.id)
    confidences = behavior_confidence(db, session.id)
    course = session.course
    teacher = getattr(course, "teacher", None)
    duration = _duration_seconds(session)

    focused_total = sum(totals.get(key, 0) for key in config.FOCUSED_BEHAVIORS)
    unfocused_total = sum(totals.get(key, 0) for key in config.UNFOCUSED_BEHAVIORS)
    grand_total = focused_total + unfocused_total

    behavior_rows = [
        {
            "key": key,
            "name_cn": config.behavior_cn(key),
            "name_en": config.behavior_en(key),
            "count": totals.get(key, 0),
            "ratio": round(totals.get(key, 0) / grand_total * 100, 2) if grand_total else 0.0,
            "avg_confidence": confidences.get(key, 0.0),
            "weight": config.ATTENTION_WEIGHTS.get(key, 0.0),
            "focused": key in config.FOCUSED_BEHAVIORS,
        }
        for key in config.BEHAVIOR_ORDER
    ]

    student_count = max(
        [
            int(row or 0)
            for row in db.execute(
                select(func.max(AttentionRecord.student_count)).where(
                    AttentionRecord.session_id == session.id
                )
            ).scalars().all()
        ]
        or [0]
    )

    return {
        "session_id": session.id,
        "course_name": getattr(course, "course_name", ""),
        "class_name": getattr(course, "class_name", ""),
        "classroom": getattr(course, "classroom", ""),
        "teacher_name": getattr(teacher, "real_name", "") or getattr(teacher, "username", ""),
        "start_time": session.start_time.isoformat() if session.start_time else "",
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "duration_minutes": round(duration / 60, 1),
        "status": session.status,
        "student_count": student_count,
        "focused_count": focused_total,
        "unfocused_count": unfocused_total,
        "record_count": aggregates["record_count"],
        "behaviors": behavior_rows,
        "behavior_totals": totals,
        "attention_series": attention_series(db, session.id),
        "distribution": bucket_distribution(scores),
        "summary": _summary_text(
            session, aggregates, totals, focused_total, unfocused_total, grand_total
        ),
        **aggregates,
    }


def session_statistics(db: Session, session: ClassSession) -> dict[str, Any]:
    """课堂统计明细（供报告页面的各图表使用）。"""
    scores = attention_scores(db, session.id)
    series = attention_series(db, session.id)
    behaviors = behavior_series(db, session.id)
    return {
        "session_id": session.id,
        "attention_series": series,
        "behavior_series": behaviors,
        "distribution": bucket_distribution(scores),
        "ratio_series": [
            {
                "name": item["name_cn"],
                "key": item["key"],
                "value": item["count"],
                "ratio": item["ratio"],
            }
            for item in behaviors
        ],
        "aggregates": aggregate_scores(scores),
    }


def _summary_text(
    session: ClassSession,
    aggregates: dict[str, Any],
    totals: dict[str, int],
    focused_total: int,
    unfocused_total: int,
    grand_total: int,
) -> list[str]:
    """根据统计数据生成课堂总结（若干句中文描述）。"""
    lines: list[str] = []
    if aggregates["record_count"] == 0:
        lines.append("本节课堂尚未产生检测数据，建议使用图片检测、视频检测或实时课堂功能采集数据后再查看报告。")
        return lines

    lines.append(
        f"本节课堂共完成 {aggregates['record_count']} 次专注度采样，"
        f"平均专注度 {aggregates['avg_attention']}%，整体评价为“{aggregates['level']}”。"
    )
    fluctuation = round(
        (aggregates["max_attention"] or 0) - (aggregates["min_attention"] or 0), 2
    )
    lines.append(
        f"专注度最高 {aggregates['max_attention']}%，最低 {aggregates['min_attention']}%，"
        f"波动幅度 {fluctuation} 个百分点。"
    )

    if grand_total:
        top_focused = sorted(
            ((key, totals.get(key, 0)) for key in config.FOCUSED_BEHAVIORS),
            key=lambda item: item[1],
            reverse=True,
        )
        lines.append(
            "专注类行为（举手 / 阅读 / 写作）累计 "
            f"{focused_total} 人次，占比 {round(focused_total / grand_total * 100, 2)}%，"
            f"其中{config.behavior_cn(top_focused[0][0])}最多（{top_focused[0][1]} 人次）。"
        )
        unfocused_detail = "、".join(
            f"{config.behavior_cn(key)} {totals.get(key, 0)} 人次"
            for key in config.UNFOCUSED_BEHAVIORS
        )
        lines.append(
            f"非专注类行为累计 {unfocused_total} 人次，"
            f"占比 {round(unfocused_total / grand_total * 100, 2)}%（{unfocused_detail}）。"
        )
        phone_count = totals.get("using_phone", 0)
        if phone_count:
            lines.append(
                f"检测到使用手机行为 {phone_count} 人次，建议通过课堂互动或随机提问减少手机使用。"
            )
        if focused_total >= unfocused_total:
            lines.append("整体来看，学生专注行为多于非专注行为，课堂秩序良好。")
        else:
            lines.append("非专注行为数量偏多，建议调整教学节奏、增加课堂互动环节。")
    return lines


def dashboard_overview(db: Session, user: User | None = None) -> dict[str, Any]:
    """首页仪表盘统计：课程数、课堂数、今日课堂、平均专注度、最近课堂。"""
    teacher_id = None
    if user is not None and user.role != "admin":
        teacher_id = user.id

    course_statement = select(func.count(Course.id))
    if teacher_id is not None:
        course_statement = course_statement.where(Course.teacher_id == teacher_id)
    course_count = int(db.execute(course_statement).scalar() or 0)

    session_statement = select(ClassSession).join(Course, Course.id == ClassSession.course_id)
    if teacher_id is not None:
        session_statement = session_statement.where(Course.teacher_id == teacher_id)
    sessions = db.execute(session_statement).scalars().all()

    today = date.today()
    today_count = sum(1 for item in sessions if item.start_time and item.start_time.date() == today)
    running_count = sum(1 for item in sessions if item.status == "running")

    attention_statement = select(AttentionRecord.attention_score)
    if teacher_id is not None:
        attention_statement = attention_statement.join(
            ClassSession, ClassSession.id == AttentionRecord.session_id
        ).join(Course, Course.id == ClassSession.course_id).where(Course.teacher_id == teacher_id)
    scores = [float(value) for value in db.execute(attention_statement).scalars().all() if value]
    average = round(sum(scores) / len(scores), 2) if scores else None

    recent = sorted(sessions, key=lambda item: item.start_time or datetime.min, reverse=True)[:8]
    recent_rows = [session_card(db, item) for item in recent]
    trend = [
        {
            "label": item["date"][5:] if item["date"] else "",
            "value": item["avg_attention"],
            "course_name": item["course_name"],
            "session_id": item["id"],
        }
        for item in reversed(recent_rows)
        if item["avg_attention"] is not None
    ]

    return {
        "course_count": course_count,
        "session_count": len(sessions),
        "today_session_count": today_count,
        "running_session_count": running_count,
        "avg_attention": average,
        "recent_sessions": recent_rows,
        "attention_trend": trend,
    }
