# -*- coding: utf-8 -*-
"""检测业务服务：串联 YOLOv8 检测 -> 行为统计 -> 专注度计算 -> 数据库落库。

图片检测接口、视频检测后台任务、WebSocket 实时检测都复用本模块，
避免同一套流程在多处重复实现（对应修改报告第 10.4、27 节）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

import config
from database.models import AttentionRecord, DetectionRecord
from detection.attention import AttentionResult, calculate_attention
from detection.behavior import BehaviorSummary, detail_list, summarize_detections
from detection.detector import Detection, get_detector
from detection.image_utils import bgr_to_base64, draw_detections, draw_hud


@dataclass
class AnalysisResult:
    """一次检测（一帧图像）的完整分析结果。"""

    detections: list[Detection] = field(default_factory=list)
    summary: BehaviorSummary = field(default_factory=BehaviorSummary)
    attention: AttentionResult | None = None
    detect_time: float = 0.0
    saved: bool = False

    def payload(self) -> dict[str, Any]:
        """转换为可直接返回给前端的 JSON 结构。"""
        return {
            "detect_time": round(self.detect_time, 3),
            "detections": detail_list(self.detections),
            "behaviors": self.summary.items(),
            "counts": {
                key: self.summary.counts.get(key, 0) for key in config.BEHAVIOR_ORDER
            },
            "student_count": self.summary.student_count,
            "focused_count": self.summary.focused_count,
            "unfocused_count": self.summary.unfocused_count,
            "attention": self.attention.to_dict() if self.attention else {},
            "saved": self.saved,
        }


def analyze_image(
    image: np.ndarray,
    conf: float | None = None,
    with_plot: bool = False,
    jpeg_quality: int = 75,
    hud: bool = False,
) -> tuple[AnalysisResult, np.ndarray | None]:
    """对单张图像执行完整分析：YOLOv8 检测 -> 行为统计 -> 专注度计算。

    :param with_plot: 是否返回绘制了检测框的图像；
    :param hud: 是否在图像上叠加专注度信息面板（实时画面使用）。
    """
    detector = get_detector()
    started = time.perf_counter()
    detections = detector.detect(image, conf=conf)
    detect_time = time.perf_counter() - started

    summary = summarize_detections(detections)
    attention = calculate_attention(summary.counts)
    result = AnalysisResult(
        detections=detections, summary=summary, attention=attention, detect_time=detect_time
    )

    plotted: np.ndarray | None = None
    if with_plot:
        plotted = draw_detections(image, [item.to_dict() for item in detections])
        if hud:
            plotted = draw_hud(plotted, _hud_lines(summary, attention))
    return result, plotted


def _hud_lines(summary: BehaviorSummary, attention: AttentionResult) -> list[str]:
    """实时画面左上角信息面板的文字内容。"""
    score_text = f"{attention.score:.1f}%" if attention.score is not None else "--"
    return [
        f"课堂专注度：{score_text}  ({attention.level})",
        f"学生人数：{summary.student_count}",
        "  ".join(
            f"{config.behavior_cn(key)} {summary.counts.get(key, 0)}"
            for key in config.FOCUSED_BEHAVIORS
        ),
        "  ".join(
            f"{config.behavior_cn(key)} {summary.counts.get(key, 0)}"
            for key in config.UNFOCUSED_BEHAVIORS
        ),
    ]


def plot_detections(image: np.ndarray, detections: list[Detection]) -> np.ndarray:
    """绘制检测框（供需要单独出图的场景使用）。"""
    return draw_detections(image, [item.to_dict() for item in detections])


def image_to_data_uri(image: np.ndarray, quality: int = 75) -> str:
    """标注图像 -> dataURI，便于直接在前端 <img> 中显示。"""
    return bgr_to_base64(image, quality=quality)


def record_result(
    db: Session,
    session_id: int,
    summary: BehaviorSummary,
    attention: AttentionResult,
    frame_index: int = 0,
    timestamp: datetime | None = None,
    confidence_threshold: float | None = None,
) -> None:
    """把一次检测结果写入行为检测记录表与专注度记录表。"""
    moment = timestamp or datetime.now()
    threshold = float(
        config.CONF_THRESHOLD if confidence_threshold is None else confidence_threshold
    )
    for key in config.BEHAVIOR_ORDER:
        count = int(summary.counts.get(key, 0))
        if count <= 0:
            continue
        db.add(
            DetectionRecord(
                session_id=session_id,
                behavior_type=key,
                person_count=count,
                avg_confidence=float(summary.confidences.get(key, 0.0)),
                frame_index=frame_index,
                detection_time=moment,
            )
        )
    db.add(
        AttentionRecord(
            session_id=session_id,
            student_count=int(summary.student_count),
            focused_count=int(attention.focused_count),
            unfocused_count=int(attention.unfocused_count),
            attention_score=float(attention.score or 0.0),
            confidence_threshold=threshold,
            record_time=moment,
        )
    )
    db.commit()


def mark_analysis_mode(db: Session, session: Any, mode: str) -> None:
    """记录该课堂使用过的分析方式（图片 / 视频 / 实时）。"""
    if session is None:
        return
    if session.analysis_mode == mode:
        return
    # 同一课堂可能混合使用多种方式，用 + 连接便于报告中说明
    modes = [item for item in (session.analysis_mode or "").split("+") if item]
    if mode not in modes:
        modes.append(mode)
    session.analysis_mode = "+".join(modes)
    db.commit()


def session_payload(session: Any) -> dict[str, Any]:
    """课堂对象 -> 前端需要的 JSON 结构。"""
    course = getattr(session, "course", None)
    return {
        "id": session.id,
        "course_id": session.course_id,
        "course_name": getattr(course, "course_name", ""),
        "class_name": getattr(course, "class_name", ""),
        "classroom": getattr(course, "classroom", ""),
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "duration": session.duration,
        "duration_minutes": session.duration_minutes,
        "status": session.status,
    }
