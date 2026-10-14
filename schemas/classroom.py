# -*- coding: utf-8 -*-
"""课堂管理相关的数据结构。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionStart(BaseModel):
    """开始一次课堂。"""

    course_id: int = Field(..., description="课程ID")


class SessionOut(BaseModel):
    """课堂基础信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    course_name: str = ""
    class_name: str = ""
    classroom: str = ""
    teacher_name: str = ""
    start_time: datetime
    end_time: datetime | None = None
    duration: int = 0
    duration_minutes: float = 0.0
    status: str = "running"
    avg_attention: float | None = None
    max_attention: float | None = None
    min_attention: float | None = None
    student_count: int = 0
    record_count: int = 0
    level: str = ""
    date: str = ""
    time_range: str = ""


class SessionDetail(SessionOut):
    """课堂详情（含行为统计与专注度统计）。"""

    behavior_totals: dict[str, int] = {}
    attention_series: list[dict] = []
