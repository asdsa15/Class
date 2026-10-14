# -*- coding: utf-8 -*-
"""课堂行为检测与专注度计算包。

* detector.py    YOLOv8 课堂行为检测（Web 后端可调用的服务类）
* behavior.py    行为统计（把检测结果汇总为 6 类行为的数量与置信度）
* attention.py   专注度计算（行为权重 -> 课堂专注度）
* image_utils.py 图像读写、检测框绘制、base64 编解码等工具函数
"""

from detection.attention import AttentionResult, calculate_attention  # noqa: F401
from detection.behavior import BehaviorSummary, summarize_detections  # noqa: F401
from detection.detector import ClassroomDetector, Detection, get_detector  # noqa: F401

__all__ = [
    "Detection",
    "ClassroomDetector",
    "get_detector",
    "BehaviorSummary",
    "summarize_detections",
    "AttentionResult",
    "calculate_attention",
]
