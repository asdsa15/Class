# -*- coding: utf-8 -*-
"""课堂行为检测接口（对应修改报告第 10.4、27 节）。

包含三种检测方式：

* POST /api/detection/image               图片检测（同步返回检测结果与标注图）
* POST /api/detection/video               视频检测（后台任务，前端轮询进度）
* WS   /ws/classroom/{session_id}         实时课堂检测（浏览器帧上传 / 服务器摄像头）

三种方式最终都复用 services/detection_service.py 的同一条算法链：
YOLOv8 -> 行为统计 -> 专注度计算 -> 数据库落库。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

import config
from database.database import SessionLocal, get_db
from database.models import ClassSession, User
from detection.detector import ModelUnavailableError, get_detector
from detection.image_utils import base64_to_bgr, decode_image_bytes, imwrite, resize_max_side
from routers.auth import get_current_user
from routers.classroom import get_session_or_404
from schemas.detection import DetectionResponse, VideoTaskOut
from services import detection_service, video_service
from services.security import decode_token

logger = logging.getLogger("classroom.detection")

router = APIRouter(tags=["课堂行为检测"])


# ---------------------------------------------------------------------------
# 公共工具
# ---------------------------------------------------------------------------
def _safe_name(filename: str | None) -> str:
    """过滤上传文件名，避免路径穿越等问题。"""
    name = Path(filename or "upload").name
    return "".join(ch for ch in name if ch.isalnum() or ch in {"-", "_", ".", " "}).strip() or "upload"


def _check_session_access(db: Session, session_id: int | None, user: User) -> ClassSession | None:
    if not session_id:
        return None
    session = get_session_or_404(db, session_id)
    if user.role != "admin" and session.course.teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作其他教师的课堂")
    return session


def _payload_from(result: detection_service.AnalysisResult) -> dict[str, Any]:
    return result.payload()


# ---------------------------------------------------------------------------
# 1. 图片检测
# ---------------------------------------------------------------------------
@router.post("/api/detection/image", response_model=DetectionResponse, summary="图片课堂行为检测")
async def detect_image(
    file: UploadFile = File(..., description="待检测的课堂图片"),
    session_id: int | None = Form(None, description="关联的课堂ID（用于把结果写入数据库）"),
    save: bool = Form(False, description="是否把本次检测结果保存到课堂记录"),
    return_base64: bool = Form(True, description="是否在响应中直接返回标注图（dataURI）"),
    conf: float | None = Form(None, description="置信度阈值，缺省使用系统配置"),
    with_box: bool = Form(True, description="是否绘制检测框"),
    hud: bool = Form(False, description="是否叠加专注度信息面板"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    filename = _safe_name(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in config.ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的图片格式：{suffix or '未知'}",
        )

    session = _check_session_access(db, session_id, user)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")

    image = decode_image_bytes(content)
    if image is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片解析失败")

    try:
        result, plotted = await run_in_threadpool(
            detection_service.analyze_image,
            image,
            conf,
            with_box,
            config.REALTIME_JPEG_QUALITY,
            hud,
        )
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    payload = _payload_from(result)
    payload.update({"success": True, "filename": filename, "source_size": (image.shape[1], image.shape[0])})

    if plotted is not None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = config.RESULT_DIR / f"image_{stamp}_{Path(filename).stem}.jpg"
        await run_in_threadpool(imwrite, output_path, plotted)
        payload["image_url"] = f"/results/{output_path.name}"
        if return_base64:
            payload["image_base64"] = detection_service.image_to_data_uri(
                plotted, quality=config.REALTIME_JPEG_QUALITY
            )

    if save and session is not None:
        await run_in_threadpool(
            detection_service.record_result, db, session.id, result.summary, result.attention
        )
        await run_in_threadpool(detection_service.mark_analysis_mode, db, session, "image")
        payload["saved"] = True
        payload["session_id"] = session.id
        payload["message"] = "检测结果已写入课堂记录"
    elif save and session is None:
        payload["message"] = "未选择课堂，检测结果未保存"
    else:
        payload["message"] = "检测完成（预览模式，未写入数据库）"

    return payload


# ---------------------------------------------------------------------------
# 2. 视频检测（后台任务）
# ---------------------------------------------------------------------------
@router.post("/api/detection/video", response_model=VideoTaskOut, summary="提交视频检测任务")
async def detect_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="待检测的课堂视频"),
    session_id: int | None = Form(None, description="关联的课堂ID（结果写入该课堂）"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    filename = _safe_name(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in config.ALLOWED_VIDEO_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的视频格式：{suffix or '未知'}",
        )

    session = _check_session_access(db, session_id, user)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_path = config.UPLOAD_DIR / f"{stamp}_{filename}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")
    input_path.write_bytes(content)

    output_path = config.RESULT_DIR / f"{Path(filename).stem}_detect_{stamp}.mp4"
    task = video_service.create_task(
        filename, input_path, output_path, session.id if session else None, user.id
    )
    background_tasks.add_task(video_service.process_video, task["task_id"])
    logger.info("已提交视频检测任务：%s（%s）", task["task_id"], filename)
    task["message"] = "视频已上传，正在后台检测（每 N 帧检测一次，请轮询进度）"
    return task


@router.get("/api/detection/video/{task_id}", response_model=VideoTaskOut, summary="查询视频检测进度")
def video_task_status(
    task_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    task = video_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="检测任务不存在或已过期")
    if user.role != "admin" and task.get("owner_id") != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看其他用户的检测任务")
    return task


@router.get("/api/detection/videos", summary="最近的视频检测任务")
def list_video_tasks(
    limit: int = 10,
    user: User = Depends(get_current_user),
) -> list[dict]:
    return video_service.list_tasks(limit=limit, owner_id=user.id, is_admin=user.role == "admin")


# ---------------------------------------------------------------------------
# 3. 实时课堂检测（WebSocket）
# ---------------------------------------------------------------------------
class _RealtimeState:
    """一次 WebSocket 连接的运行状态。"""

    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        self.last_record = 0.0
        self.frame_index = 0
        self.frame_count = 0
        self.scores: list[float] = []
        self.mode_marked = False
        self.send_lock = asyncio.Lock()
        self.camera_task: asyncio.Task | None = None

    async def send(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        async with self.send_lock:
            await websocket.send_text(json.dumps(message, ensure_ascii=False))

    def maybe_record(self, db: Session, result: detection_service.AnalysisResult) -> bool:
        """按配置的时间间隔把检测结果写入数据库。"""
        if result.attention is None or result.attention.score is None:
            return False
        now = time.monotonic()
        if now - self.last_record < config.REALTIME_RECORD_INTERVAL:
            return False
        self.last_record = now
        detection_service.record_result(
            db,
            self.session_id,
            result.summary,
            result.attention,
            frame_index=self.frame_index,
        )
        if not self.mode_marked:
            session_row = db.get(ClassSession, self.session_id)
            detection_service.mark_analysis_mode(db, session_row, "realtime")
            self.mode_marked = True
        return True

    def stop_camera(self) -> None:
        if self.camera_task and not self.camera_task.done():
            self.camera_task.cancel()
        self.camera_task = None


def _ws_authenticate(token: str | None) -> User | None:
    """WebSocket 登录校验：支持 ?token= 查询参数或登录 Cookie。"""
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    db = SessionLocal()
    try:
        return db.execute(select(User).where(User.username == payload.get("sub"))).scalar_one_or_none()
    finally:
        db.close()


def _analyze_frame(state: _RealtimeState, db: Session, image: Any) -> dict[str, Any]:
    """在工作线程中执行：检测 + 统计 + 专注度 + 可选落库。"""
    image = resize_max_side(image, config.REALTIME_MAX_SIDE)
    result, plotted = detection_service.analyze_image(
        image,
        with_plot=True,
        jpeg_quality=config.REALTIME_JPEG_QUALITY,
        hud=True,
    )
    state.frame_index += 1
    state.frame_count += 1
    if result.attention and result.attention.score is not None:
        state.scores.append(float(result.attention.score))
    saved = state.maybe_record(db, result)

    payload = result.payload()
    payload.update(
        {
            "type": "result",
            "time": datetime.now().strftime("%H:%M:%S"),
            "frame_index": state.frame_index,
            "saved": saved,
            "frame": detection_service.image_to_data_uri(
                plotted, quality=config.REALTIME_JPEG_QUALITY
            ),
        }
    )
    return payload


async def _camera_loop(websocket: WebSocket, state: _RealtimeState, device: int) -> None:
    """服务器端摄像头实时检测：读取本机摄像头并持续推送检测结果。"""
    capture = await run_in_threadpool(cv2.VideoCapture, device)
    if not capture.isOpened():
        await run_in_threadpool(capture.release)
        await state.send(
            websocket,
            {"type": "error", "message": f"无法打开摄像头（设备号 {device}），请检查摄像头是否可用"},
        )
        return

    db = SessionLocal()
    db_interval = time.monotonic()
    try:
        await state.send(websocket, {"type": "camera_started", "device": device})
        while True:
            ok, frame = await run_in_threadpool(capture.read)
            if not ok:
                await state.send(websocket, {"type": "error", "message": "摄像头读取失败，已停止"})
                break
            payload = await run_in_threadpool(_analyze_frame, state, db, frame)
            await state.send(websocket, payload)
            if time.monotonic() - db_interval > 60:  # 长连接时定期回收会话，避免连接失效
                db.close()
                db = SessionLocal()
                db_interval = time.monotonic()
            await asyncio.sleep(config.REALTIME_CAMERA_INTERVAL)
    except asyncio.CancelledError:
        raise
    except ModelUnavailableError as exc:
        await state.send(websocket, {"type": "error", "message": str(exc)})
    except Exception as exc:  # pragma: no cover - 运行时兜底
        logger.exception("摄像头实时检测异常")
        await state.send(websocket, {"type": "error", "message": f"摄像头检测异常：{exc}"})
    finally:
        await run_in_threadpool(capture.release)
        db.close()
        await state.send(websocket, {"type": "camera_stopped"})


@router.websocket("/ws/ping")
async def websocket_ping(websocket: WebSocket) -> None:
    """实时检测服务的连通性探测。

    首页用它来显示「实时检测服务」状态：能正常握手并收到 pong 即视为可用，
    不涉及课堂数据，也不需要登录。
    """
    await websocket.accept()
    await websocket.send_text(
        json.dumps(
            {
                "type": "pong",
                "service": "classroom-realtime",
                "time": datetime.now().strftime("%H:%M:%S"),
            },
            ensure_ascii=False,
        )
    )
    await websocket.close(code=1000)


@router.websocket("/ws/classroom/{session_id}")
async def classroom_realtime(websocket: WebSocket, session_id: int) -> None:
    """实时课堂检测 WebSocket。

    前端可发送的消息类型：

    * {"type": "frame", "image": "data:image/jpeg;base64,..."}  浏览器摄像头 / 视频帧
    * {"type": "start_camera", "device": 0}                     使用服务器本机摄像头
    * {"type": "stop_camera"}                                   停止服务器摄像头
    * {"type": "ping"}                                          心跳

    服务端返回 {"type": "result", ...}，其中包含标注画面、行为数量与专注度。
    """
    token = websocket.query_params.get("token") or websocket.cookies.get(config.COOKIE_NAME)
    user = _ws_authenticate(token)
    if user is None:
        await websocket.close(code=4401, reason="未登录或登录状态已失效")
        return

    db = SessionLocal()
    state: _RealtimeState | None = None
    try:
        session = db.get(ClassSession, session_id)
        if session is None:
            await websocket.close(code=4404, reason="课堂不存在")
            return
        if user.role != "admin" and session.course.teacher_id != user.id:
            await websocket.close(code=4403, reason="无权访问该课堂")
            return

        await websocket.accept()
        state = _RealtimeState(session_id)
        detector = get_detector()
        await state.send(
            websocket,
            {
                "type": "ready",
                "message": "实时课堂检测已连接",
                "session": detection_service.session_payload(session),
                "model": detector.status(),
                "weights": config.ATTENTION_WEIGHTS,
                "record_interval": config.REALTIME_RECORD_INTERVAL,
                "student_count": 0,
                "attention_score": None,
                "behaviors": {key: 0 for key in config.BEHAVIOR_ORDER},
            },
        )

        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await state.send(websocket, {"type": "error", "message": "消息格式错误，需要 JSON"})
                continue

            action = message.get("type", "frame")
            if action == "ping":
                await state.send(websocket, {"type": "pong", "time": datetime.now().isoformat(timespec="seconds")})
                continue

            if action == "start_camera":
                if state.camera_task and not state.camera_task.done():
                    await state.send(websocket, {"type": "info", "message": "摄像头已在运行"})
                    continue
                device = int(message.get("device", 0) or 0)
                state.camera_task = asyncio.create_task(_camera_loop(websocket, state, device))
                continue

            if action == "stop_camera":
                state.stop_camera()
                await state.send(websocket, {"type": "camera_stopped"})
                continue

            if action != "frame":
                await state.send(websocket, {"type": "error", "message": f"不支持的消息类型：{action}"})
                continue

            image = base64_to_bgr(message.get("image", ""))
            if image is None:
                await state.send(websocket, {"type": "error", "message": "图像解析失败"})
                continue
            try:
                payload = await run_in_threadpool(_analyze_frame, state, db, image)
            except ModelUnavailableError as exc:
                await state.send(websocket, {"type": "error", "message": str(exc)})
                continue
            await state.send(websocket, payload)
    except WebSocketDisconnect:
        logger.info("实时课堂连接断开：session_id=%s", session_id)
    finally:
        if state is not None:
            state.stop_camera()
        db.close()
