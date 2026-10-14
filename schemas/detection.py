# -*- coding: utf-8 -*-
"""检测接口相关的数据结构。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BehaviorItem(BaseModel):
    """单类行为统计。"""

    key: str
    name_cn: str
    name_en: str
    count: int
    ratio: float
    avg_confidence: float
    weight: float
    focused: bool


class DetectionItem(BaseModel):
    """单个检测目标。"""

    class_id: int
    class_name: str
    behavior_key: str
    behavior_cn: str
    confidence: float
    xyxy: list[float]


class DetectionResponse(BaseModel):
    """图片检测结果。"""

    success: bool = True
    filename: str = ""
    image_url: str | None = Field(None, description="标注后的图片访问地址")
    image_base64: str | None = Field(None, description="标注后的图片 dataURI（可选返回）")
    source_size: tuple[int, int] | None = Field(None, description="原图宽高")
    detect_time: float = Field(0.0, description="本帧推理耗时（秒）")
    detections: list[DetectionItem] = []
    behaviors: list[BehaviorItem] = []
    counts: dict[str, int] = {}
    student_count: int = 0
    focused_count: int = 0
    unfocused_count: int = 0
    attention: dict[str, Any] = {}
    session_id: int | None = None
    saved: bool = False
    message: str = ""


class VideoTaskOut(BaseModel):
    """视频检测后台任务状态。"""

    task_id: str
    status: str = "pending"
    progress: float = 0.0
    message: str = ""
    filename: str = ""
    session_id: int | None = None
    total_frames: int = 0
    processed_frames: int = 0
    detected_frames: int = 0
    avg_attention: float | None = None
    attention_scores: list[float] = []
    result_video_url: str | None = None
    error: str | None = None
    created_at: str = ""
    finished_at: str | None = None


class SystemStatus(BaseModel):
    """系统运行状态。"""

    app_name: str
    version: str
    model: dict[str, Any]
    database: dict[str, Any]
    config: dict[str, Any] = {}
