# -*- coding: utf-8 -*-
"""业务数据模型（对应修改报告第 17 节数据库设计）。

共 5 张业务表：

* user             用户（登录账号、密码哈希、角色权限）
* course           课程（课程名称、授课教师、班级、教室）
* class_session    课堂记录（开始时间、结束时间、时长、状态）
* detection_record 行为检测记录（某时刻某类行为的人数与平均置信度）
* attention_record 专注度记录（学生数、专注人数、不专注人数、专注度）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class User(Base):
    """用户表。"""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="用户ID")
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False, comment="登录账号")
    password: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希值")
    real_name: Mapped[str] = mapped_column(String(50), default="", comment="姓名")
    role: Mapped[str] = mapped_column(String(20), default="teacher", comment="角色：admin 管理员 / teacher 教师")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="账号状态：1 正常 / 0 已禁用")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近更新时间")
    last_login_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近登录时间")

    courses: Mapped[list["Course"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username}({self.role})>"

    @property
    def is_active(self) -> bool:
        """账号是否可用（未被管理员禁用）。"""
        return int(self.status if self.status is not None else 0) == 1

    @property
    def status_name(self) -> str:
        import config

        return config.USER_STATUS.get(int(self.status if self.status is not None else 0), "未知")


class Course(Base):
    """课程表。"""

    __tablename__ = "course"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="课程ID")
    course_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="课程名称")
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, comment="授课教师ID"
    )
    class_name: Mapped[str] = mapped_column(String(50), default="", comment="班级")
    classroom: Mapped[str] = mapped_column(String(50), default="", comment="上课教室")
    description: Mapped[str] = mapped_column(Text, default="", comment="课程简介")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")

    teacher: Mapped["User"] = relationship(back_populates="courses")
    sessions: Mapped[list["ClassSession"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Course {self.course_name}>"


class ClassSession(Base):
    """课堂记录表：一次完整的课堂检测过程。"""

    __tablename__ = "class_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="课堂ID")
    course_id: Mapped[int] = mapped_column(
        ForeignKey("course.id", ondelete="CASCADE"), index=True, comment="所属课程ID"
    )
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="开始时间")
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")
    duration: Mapped[int] = mapped_column(Integer, default=0, comment="课堂时长（秒）")
    status: Mapped[str] = mapped_column(
        String(20), default="running", index=True, comment="状态：running 进行中 / finished 已结束"
    )
    analysis_mode: Mapped[str] = mapped_column(
        String(20), default="", comment="分析方式：image 图片 / video 视频 / realtime 实时"
    )
    video_path: Mapped[str] = mapped_column(String(255), default="", comment="原始视频路径（视频分析）")
    result_video_path: Mapped[str] = mapped_column(String(255), default="", comment="结果视频路径（视频分析）")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人用户ID")

    course: Mapped["Course"] = relationship(back_populates="sessions")
    detection_records: Mapped[list["DetectionRecord"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    attention_records: Mapped[list["AttentionRecord"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    @property
    def duration_minutes(self) -> float:
        """课堂时长（分钟，保留一位小数）。"""
        return round(self.duration / 60, 1)

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClassSession #{self.id} course={self.course_id} {self.status}>"


class DetectionRecord(Base):
    """课堂行为检测记录表。

    一条记录表示"某个时刻检测到某类行为的学生人数"，
    person_count 为该时刻该类行为的人数，avg_confidence 为这些目标的平均置信度。
    """

    __tablename__ = "detection_record"
    __table_args__ = (Index("ix_detection_session_behavior", "session_id", "behavior_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="记录ID")
    session_id: Mapped[int] = mapped_column(
        ForeignKey("class_session.id", ondelete="CASCADE"), index=True, comment="课堂ID"
    )
    behavior_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="行为类型（英文键）")
    person_count: Mapped[int] = mapped_column(Integer, default=0, comment="该行为人数")
    avg_confidence: Mapped[float] = mapped_column(Float, default=0.0, comment="平均置信度")
    frame_index: Mapped[int] = mapped_column(Integer, default=0, comment="视频帧序号（实时检测为 0）")
    detection_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="检测时间"
    )

    session: Mapped["ClassSession"] = relationship(back_populates="detection_records")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DetectionRecord {self.behavior_type} x{self.person_count}>"


class AttentionRecord(Base):
    """课堂专注度记录表。"""

    __tablename__ = "attention_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="记录ID")
    session_id: Mapped[int] = mapped_column(
        ForeignKey("class_session.id", ondelete="CASCADE"), index=True, comment="课堂ID"
    )
    student_count: Mapped[int] = mapped_column(Integer, default=0, comment="学生人数")
    focused_count: Mapped[int] = mapped_column(Integer, default=0, comment="专注人数")
    unfocused_count: Mapped[int] = mapped_column(Integer, default=0, comment="不专注人数")
    attention_score: Mapped[float] = mapped_column(Float, default=0.0, comment="课堂专注度（%）")
    confidence_threshold: Mapped[float] = mapped_column(
        Float, default=0.0, comment="本次检测使用的置信度阈值"
    )
    record_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="记录时间"
    )

    session: Mapped["ClassSession"] = relationship(back_populates="attention_records")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AttentionRecord {self.attention_score}%>"
