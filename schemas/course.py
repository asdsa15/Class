# -*- coding: utf-8 -*-
"""课程管理相关的数据结构。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    """新建课程。"""

    course_name: str = Field(..., min_length=1, max_length=100, description="课程名称")
    class_name: str = Field("", max_length=50, description="班级")
    classroom: str = Field("", max_length=50, description="上课教室")
    description: str = Field("", description="课程简介")
    teacher_id: int | None = Field(None, description="授课教师ID（管理员可指定，默认当前用户）")


class CourseUpdate(BaseModel):
    """修改课程（字段可选）。"""

    course_name: str | None = Field(None, min_length=1, max_length=100)
    class_name: str | None = Field(None, max_length=50)
    classroom: str | None = Field(None, max_length=50)
    description: str | None = None
    teacher_id: int | None = None


class CourseOut(BaseModel):
    """课程信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    course_name: str
    teacher_id: int
    teacher_name: str = ""
    class_name: str = ""
    classroom: str = ""
    description: str = ""
    create_time: datetime | None = None
    session_count: int = 0
    avg_attention: float | None = None
