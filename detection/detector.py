# -*- coding: utf-8 -*-
"""YOLOv8 课堂行为检测服务类。

原项目在 MainProgram.py 中把 YOLO 推理与 Qt 界面、视频、文件操作混在一起，
不适合 Web 后端调用（对应修改报告第 9、10 节）。本模块把"检测"能力抽取为
独立、无界面、可被 FastAPI 任意调用的服务类：

    输入图片 -> YOLOv8 -> 结构化检测结果（类别 / 置信度 / 坐标）

模型采用延迟加载 + 全局单例：首次检测时才加载权重，避免服务启动过慢，
同时保证多个请求复用同一个模型实例；推理时加锁，避免多线程同时调用。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

import config
from detection.image_utils import draw_detections

logger = logging.getLogger("classroom.detector")


class ModelUnavailableError(RuntimeError):
    """模型不可用：未安装 ultralytics、权重文件缺失或加载失败。"""


def normalize_behavior_key(name: str | None, class_id: int | None = None) -> str:
    """把模型输出的类别名称归一化为系统统一使用的行为英文键。"""
    if name:
        cleaned = " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())
        for alias, key in config.BEHAVIOR_ALIASES.items():
            normalized_alias = " ".join(
                alias.strip().lower().replace("_", " ").replace("-", " ").split()
            )
            if normalized_alias == cleaned:
                return key
    if class_id is not None and class_id in config.BEHAVIOR_KEYS:
        return config.BEHAVIOR_KEYS[class_id]
    return (name or f"class_{class_id}").strip()


@dataclass
class Detection:
    """单个课堂行为检测结果。"""

    class_id: int
    class_name: str
    behavior_key: str
    behavior_cn: str
    confidence: float
    xyxy: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "behavior_key": self.behavior_key,
            "behavior_cn": self.behavior_cn,
            "confidence": round(self.confidence, 4),
            "xyxy": [round(float(v), 1) for v in self.xyxy],
        }


class ClassroomDetector:
    """课堂行为检测器：封装 YOLOv8 模型的加载与推理。"""

    def __init__(
        self,
        model_path: str | Path | None = None,
        conf: float | None = None,
        iou: float | None = None,
        imgsz: int | None = None,
        device: str | None = None,
    ) -> None:
        self.model_path = Path(model_path or config.MODEL_PATH)
        self.conf = float(config.CONF_THRESHOLD if conf is None else conf)
        self.iou = float(config.IOU_THRESHOLD if iou is None else iou)
        self.imgsz = int(config.IMAGE_SIZE if imgsz is None else imgsz)
        self.device = config.DEVICE if device is None else device
        self._model: Any = None
        self._names: dict[int, str] = {}
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self.load_error: str | None = None
        self.load_seconds: float = 0.0
        self._inference_count = 0
        # 只统计最近 50 次推理，且不把预热那一次计入，避免平均值被首次调用拉高
        self._inference_durations: deque[float] = deque(maxlen=50)
        self._warming = False

    # ------------------------------ 加载 ------------------------------
    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> Any:
        """延迟加载 YOLOv8 模型（线程安全）。"""
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from ultralytics import YOLO
            except Exception as exc:  # ultralytics / torch 未安装
                self.load_error = f"未安装 ultralytics（{exc}）"
                raise ModelUnavailableError(
                    "YOLOv8 依赖未安装，请先执行 pip install -r requirements.txt"
                ) from exc

            if not self.model_path.exists():
                # 主模型缺失时，按配置顺序尝试备用权重（如训练输出目录中的 best.pt）
                for candidate in config.MODEL_FALLBACK_PATHS:
                    if candidate.exists():
                        logger.warning("主模型不存在（%s），改用备用权重：%s", self.model_path, candidate)
                        self.model_path = candidate
                        break
                else:
                    self.load_error = f"模型权重不存在：{self.model_path}"
                    raise ModelUnavailableError(self.load_error)

            logger.info("正在加载课堂行为检测模型：%s", self.model_path)
            started = time.perf_counter()
            try:
                model = YOLO(str(self.model_path))
            except Exception as exc:
                self.load_error = f"模型加载失败：{exc}"
                raise ModelUnavailableError(self.load_error) from exc
            self.load_seconds = round(time.perf_counter() - started, 3)

            names = getattr(model, "names", None) or config.CLASS_NAMES
            self._names = {int(k): str(v) for k, v in dict(names).items()}
            self._model = model
            self.load_error = None
            logger.info("模型加载完成（耗时 %.2f 秒），类别：%s", self.load_seconds, self._names)
            return self._model

    def warmup(self) -> None:
        """预加载并做一次空推理（与原项目启动时的预处理一致）。"""
        try:
            self.load()
            self._warming = True
            self.detect(np.zeros((64, 64, 3), dtype=np.uint8))
            self._warming = False
            logger.info("模型预热完成")
        except Exception as exc:
            self._warming = False
            logger.warning("模型预热失败：%s", exc)

    # ------------------------------ 推理 ------------------------------
    def detect(
        self,
        image: np.ndarray,
        conf: float | None = None,
        classes: Sequence[int] | None = None,
    ) -> list[Detection]:
        """对单张图像执行课堂行为检测。"""
        model = self.load()
        device = None if self.device in (None, "", "auto") else self.device
        started = time.perf_counter()
        with self._infer_lock:
            results = model.predict(
                source=image,
                conf=self.conf if conf is None else float(conf),
                iou=self.iou,
                imgsz=self.imgsz,
                max_det=config.MAX_DETECTIONS,
                device=device,
                classes=list(classes) if classes else None,
                verbose=False,
            )

        elapsed = time.perf_counter() - started
        if not self._warming:
            self._inference_count += 1
            self._inference_durations.append(elapsed)

        if not results:
            return []
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        names = dict(getattr(result, "names", None) or self._names)
        detections: list[Detection] = []
        for index in range(len(boxes)):
            class_id = int(boxes.cls[index].item())
            class_name = str(
                names.get(class_id, config.CLASS_NAMES.get(class_id, str(class_id)))
            )
            key = normalize_behavior_key(class_name, class_id)
            detections.append(
                Detection(
                    class_id=class_id,
                    class_name=class_name,
                    behavior_key=key,
                    behavior_cn=config.behavior_cn(key),
                    confidence=float(boxes.conf[index].item()),
                    xyxy=[float(v) for v in boxes.xyxy[index].tolist()],
                )
            )
        return detections

    def detect_and_plot(
        self, image: np.ndarray, conf: float | None = None
    ) -> tuple[np.ndarray, list[Detection]]:
        """检测并绘制检测框，返回（标注图像, 检测结果）。"""
        detections = self.detect(image, conf=conf)
        plotted = draw_detections(image, [item.to_dict() for item in detections])
        return plotted, detections

    # ------------------------------ 状态 ------------------------------
    def status(self) -> dict[str, Any]:
        """检测器状态，用于前端提示"模型是否已加载"。"""
        names = self._names or {int(k): v for k, v in config.CLASS_NAMES.items()}
        average_ms = (
            round(sum(self._inference_durations) / len(self._inference_durations) * 1000, 1)
            if self._inference_durations
            else None
        )
        return {
            "loaded": self.loaded,
            "model_path": str(self.model_path),
            "model_exists": self.model_path.exists(),
            "load_error": self.load_error,
            "load_seconds": self.load_seconds,
            "inference_count": self._inference_count,
            "avg_inference_ms": average_ms,
            "last_inference_ms": (
                round(self._inference_durations[-1] * 1000, 1) if self._inference_durations else None
            ),
            "conf_threshold": self.conf,
            "iou_threshold": self.iou,
            "image_size": self.imgsz,
            "device": self.device,
            "runtime_device": runtime_device(),
            "classes": {str(k): v for k, v in names.items()},
        }


def runtime_device() -> str:
    """当前推理实际使用的设备（cuda / cpu），用于前端展示与论文运行环境说明。"""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "unknown"


_detector: ClassroomDetector | None = None
_detector_lock = threading.Lock()


def get_detector(reload: bool = False) -> ClassroomDetector:
    """获取全局唯一的检测器实例。"""
    global _detector
    with _detector_lock:
        if _detector is None or reload:
            _detector = ClassroomDetector()
        return _detector


def detector_status() -> dict[str, Any]:
    """获取检测器状态（不会触发模型加载）。"""
    return get_detector().status()
