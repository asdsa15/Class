# -*- coding: utf-8 -*-
"""视频检测后台任务服务（对应修改报告第 12 节：QThread -> 后台任务）。

原项目使用 QThread 在后台保存检测视频；Web 系统改用 FastAPI 的
BackgroundTasks 执行视频检测任务，并把任务进度放在内存任务表中，
前端可以轮询 /api/detection/video/{task_id} 获取进度与结果。

处理流程：

    视频文件 -> 逐帧读取 -> 每 N 帧 YOLOv8 检测 -> 行为统计 -> 专注度计算
             -> 绘制检测框写入结果视频 -> 按时间间隔写入数据库
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2

import config
from database.database import SessionLocal
from database.models import ClassSession
from detection.attention import aggregate_scores, calculate_attention
from detection.behavior import summarize_detections
from detection.detector import ModelUnavailableError, get_detector, runtime_device
from detection.image_utils import draw_detections, draw_hud
from services import detection_service

logger = logging.getLogger("classroom.video")

_tasks: dict[str, dict[str, Any]] = {}
_tasks_lock = threading.Lock()
_MAX_TASKS = 30


def create_task(
    filename: str,
    input_path: Path,
    output_path: Path,
    session_id: int | None,
    owner_id: int | None = None,
) -> dict[str, Any]:
    """登记一个新的视频检测任务。"""
    task_id = uuid.uuid4().hex[:12]
    task = {
        "task_id": task_id,
        "owner_id": owner_id,
        "status": "pending",
        "progress": 0.0,
        "message": "任务已创建，等待开始",
        "filename": filename,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "session_id": session_id,
        "total_frames": 0,
        "processed_frames": 0,
        "detected_frames": 0,
        "fps": 0.0,
        "elapsed_seconds": 0.0,
        "eta_seconds": None,
        "device": "",
        "avg_attention": None,
        "attention_scores": [],
        "result_video_url": None,
        "error": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
    }
    with _tasks_lock:
        _tasks[task_id] = task
        if len(_tasks) > _MAX_TASKS:  # 保留最近的若干条任务，避免内存无限增长
            for key in sorted(_tasks, key=lambda item: _tasks[item]["created_at"])[:-_MAX_TASKS]:
                _tasks.pop(key, None)
    return dict(task)


def update_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    """更新任务状态。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is None:
            return None
        task.update(fields)
        return dict(task)


def get_task(task_id: str) -> dict[str, Any] | None:
    """查询任务状态（对外隐藏服务器本地路径）。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is None:
            return None
        public = {key: value for key, value in task.items() if key not in {"input_path", "output_path"}}
        public["attention_scores"] = task["attention_scores"][-500:]
    return public


def list_tasks(limit: int = 10, owner_id: int | None = None, is_admin: bool = False) -> list[dict[str, Any]]:
    """最近的视频检测任务列表；教师只能看到自己的任务，管理员可查看全部。"""
    with _tasks_lock:
        tasks = sorted(_tasks.values(), key=lambda item: item["created_at"], reverse=True)
        if not is_admin and owner_id is not None:
            tasks = [item for item in tasks if item.get("owner_id") == owner_id]
        tasks = tasks[:limit]
        return [
            {key: value for key, value in task.items() if key not in {"input_path", "output_path", "attention_scores"}}
            for task in tasks
        ]


def process_video(task_id: str) -> None:
    """执行视频检测任务（同步函数，由 BackgroundTasks 在线程池中调用）。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is None:
            logger.warning("视频任务不存在：%s", task_id)
            return
        input_path = Path(task["input_path"])
        output_path = Path(task["output_path"])
        session_id = task["session_id"]

    update_task(task_id, status="running", message="正在读取视频")
    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        update_task(task_id, status="failed", error="视频文件无法打开", message="视频文件无法打开")
        return

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        # mp4 编码器不可用时改用 AVI/XVID
        output_path = output_path.with_suffix(".avi")
        writer = cv2.VideoWriter(
            str(output_path), cv2.VideoWriter_fourcc(*"XVID"), fps, (width, height)
        )
    if not writer.isOpened():
        capture.release()
        update_task(task_id, status="failed", error="无法创建结果视频文件", message="无法创建结果视频文件")
        return

    update_task(
        task_id,
        total_frames=total_frames,
        device=runtime_device(),
        message=f"视频信息：{width}x{height}，{fps:.1f} FPS，共 {total_frames} 帧",
    )

    detector = get_detector()
    index = 0
    detected_frames = 0
    attention_scores: list[float] = []
    last_record_time = 0.0
    db_session = SessionLocal() if session_id else None
    started_at = time.monotonic()

    if db_session is not None:
        # 记录本课堂使用了视频分析方式，以及原始视频路径
        session_row = db_session.get(ClassSession, session_id)
        if session_row is not None:
            session_row.video_path = str(input_path)
            detection_service.mark_analysis_mode(db_session, session_row, "video")

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            index += 1
            should_detect = (index - 1) % max(config.VIDEO_SAMPLE_INTERVAL, 1) == 0

            if should_detect:
                detections = detector.detect(frame)
                summary = summarize_detections(detections)
                attention = calculate_attention(summary.counts)
                detected_frames += 1
                if attention.score is not None:
                    attention_scores.append(float(attention.score))
                plotted = draw_detections(frame, [item.to_dict() for item in detections])
                plotted = draw_hud(
                    plotted,
                    [
                        f"专注度：{attention.score:.1f}%" if attention.score is not None else "专注度：--",
                        f"学生人数：{summary.student_count}",
                        f"帧号：{index}",
                    ],
                )
                writer.write(plotted)

                if db_session is not None and attention.score is not None:
                    now_monotonic = time.monotonic()
                    if now_monotonic - last_record_time >= config.VIDEO_RECORD_INTERVAL:
                        detection_service.record_result(
                            db_session, session_id, summary, attention, frame_index=index
                        )
                        last_record_time = now_monotonic
            else:
                writer.write(frame)

            if total_frames and (index % 15 == 0 or index == total_frames):
                progress = round(min(index / total_frames * 100, 99.0), 1)
                elapsed = time.monotonic() - started_at
                speed = index / elapsed if elapsed > 0 else 0.0
                remaining = (total_frames - index) / speed if speed > 0 else None
                update_task(
                    task_id,
                    processed_frames=index,
                    detected_frames=detected_frames,
                    progress=progress,
                    elapsed_seconds=round(elapsed, 1),
                    fps=round(speed, 1),
                    eta_seconds=round(remaining, 1) if remaining is not None else None,
                    message=f"已处理 {index}/{total_frames} 帧，平均 {speed:.1f} FPS",
                )
    except ModelUnavailableError as exc:
        logger.error("视频检测失败（模型不可用）：%s", exc)
        update_task(task_id, status="failed", error=str(exc), message="模型不可用，视频检测失败")
        return
    except Exception as exc:  # pragma: no cover - 运行时异常兜底
        logger.exception("视频检测任务异常")
        update_task(task_id, status="failed", error=str(exc), message=f"任务异常：{exc}")
        return
    finally:
        capture.release()
        writer.release()
        if db_session is not None:
            db_session.close()

    aggregates = aggregate_scores(attention_scores)
    elapsed = time.monotonic() - started_at
    if db_session is not None:
        session_row = db_session.get(ClassSession, session_id)
        if session_row is not None:
            session_row.result_video_path = f"/results/{output_path.name}"
            db_session.commit()
        db_session.close()
    update_task(
        task_id,
        status="finished",
        progress=100.0,
        processed_frames=index,
        detected_frames=detected_frames,
        elapsed_seconds=round(elapsed, 1),
        fps=round(index / elapsed, 1) if elapsed > 0 else 0.0,
        avg_attention=aggregates["avg_attention"],
        attention_scores=attention_scores,
        result_video_url=f"/results/{output_path.name}",
        message="视频检测完成",
        finished_at=datetime.now().isoformat(timespec="seconds"),
    )
    logger.info("视频检测任务完成：%s（%d 帧，平均专注度 %s）", task_id, index, aggregates["avg_attention"])
