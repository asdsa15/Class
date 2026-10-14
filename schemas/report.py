# -*- coding: utf-8 -*-
"""课堂统计报告相关的数据结构。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReportOverview(BaseModel):
    """课堂报告总览。"""

    session_id: int
    course_name: str
    class_name: str = ""
    classroom: str = ""
    teacher_name: str = ""
    start_time: str = ""
    end_time: str | None = None
    duration_minutes: float = 0.0
    status: str = "running"
    avg_attention: float | None = None
    max_attention: float | None = None
    min_attention: float | None = None
    level: str = "无有效数据"
    student_count: int = 0
    focused_count: int = 0
    unfocused_count: int = 0
    record_count: int = 0
    behavior_totals: dict[str, int] = {}
    behaviors: list[dict[str, Any]] = []
    attention_series: list[dict[str, Any]] = []
    distribution: list[dict[str, Any]] = []
    summary: list[str] = []


class ReportStatistics(BaseModel):
    """课堂统计明细（供图表使用）。"""

    attention_series: list[dict[str, Any]] = []
    behavior_series: list[dict[str, Any]] = []
    distribution: list[dict[str, Any]] = []
    ratio_series: list[dict[str, Any]] = []


class DashboardOverview(BaseModel):
    """首页仪表盘数据。"""

    course_count: int = 0
    session_count: int = 0
    today_session_count: int = 0
    avg_attention: float | None = None
    running_session_count: int = 0
    recent_sessions: list[dict[str, Any]] = []
    attention_trend: list[dict[str, Any]] = []
