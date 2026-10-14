# -*- coding: utf-8 -*-
"""课堂行为统计模块（对应修改报告第 10.2 节）。

职责：把 YOLOv8 的检测结果汇总为"6 类行为各有多少人"，
供专注度计算、前端实时展示、数据库落库与课堂报告使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import config


def _as_dict(item: Any) -> dict[str, Any]:
    """兼容 Detection 对象与普通字典两种输入。"""
    if isinstance(item, Mapping):
        return dict(item)
    if hasattr(item, "to_dict"):
        return dict(item.to_dict())
    raise TypeError(f"无法解析的检测结果类型：{type(item)!r}")


@dataclass
class BehaviorSummary:
    """一帧（或一段视频）中 6 类课堂行为的统计结果。"""

    counts: dict[str, int] = field(default_factory=dict)
    confidences: dict[str, float] = field(default_factory=dict)
    student_count: int = 0

    @property
    def focused_count(self) -> int:
        """专注行为（举手 / 阅读 / 写作）人数。"""
        return sum(self.counts.get(key, 0) for key in config.FOCUSED_BEHAVIORS)

    @property
    def unfocused_count(self) -> int:
        """不专注行为（玩手机 / 低头 / 趴桌）人数。"""
        return sum(self.counts.get(key, 0) for key in config.UNFOCUSED_BEHAVIORS)

    def ratios(self) -> dict[str, float]:
        """各行为占比（%）。"""
        total = self.student_count or 1
        return {key: round(value / total * 100, 2) for key, value in self.counts.items()}

    def items(self) -> list[dict[str, Any]]:
        """按固定顺序返回行为明细，便于前端表格与图表直接使用。"""
        ratios = self.ratios()
        return [
            {
                "key": key,
                "name_cn": config.behavior_cn(key),
                "name_en": config.behavior_en(key),
                "count": self.counts.get(key, 0),
                "ratio": ratios.get(key, 0.0),
                "avg_confidence": round(self.confidences.get(key, 0.0), 4),
                "weight": config.ATTENTION_WEIGHTS.get(key, 0.0),
                "focused": key in config.FOCUSED_BEHAVIORS,
            }
            for key in config.BEHAVIOR_ORDER
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_count": self.student_count,
            "focused_count": self.focused_count,
            "unfocused_count": self.unfocused_count,
            "counts": {key: self.counts.get(key, 0) for key in config.BEHAVIOR_ORDER},
            "items": self.items(),
        }


def summarize_detections(detections: Iterable[Any]) -> BehaviorSummary:
    """把检测结果列表统计为 BehaviorSummary。

    * 每一个检测框视为一名学生的一次行为，学生人数 = 检测框总数；
    * 平均置信度按行为类别分别计算，供报告中的检测质量分析使用。
    """
    counts = {key: 0 for key in config.BEHAVIOR_ORDER}
    confidence_sum = {key: 0.0 for key in config.BEHAVIOR_ORDER}
    total = 0

    for raw in detections:
        item = _as_dict(raw)
        key = item.get("behavior_key")
        if not key:
            key = config.BEHAVIOR_KEYS.get(int(item.get("class_id", -1)))
        key = str(key or "unknown")
        if key not in counts:
            counts[key] = 0
            confidence_sum[key] = 0.0
        counts[key] += 1
        confidence_sum[key] += float(item.get("confidence", 0.0))
        total += 1

    confidences = {
        key: (confidence_sum[key] / counts[key] if counts[key] else 0.0) for key in counts
    }
    return BehaviorSummary(counts=counts, confidences=confidences, student_count=total)


def behavior_counts(detections: Iterable[Any]) -> dict[str, int]:
    """仅返回行为数量字典（供专注度算法直接使用）。"""
    return summarize_detections(detections).counts


def detail_list(detections: Sequence[Any], limit: int = 300) -> list[dict[str, Any]]:
    """返回检测框明细（前端逐目标展示类别与置信度）。"""
    items = [_as_dict(raw) for raw in detections[:limit]]
    for item in items:
        item["confidence"] = round(float(item.get("confidence", 0.0)), 4)
        item["behavior_cn"] = item.get("behavior_cn") or config.behavior_cn(
            item.get("behavior_key", "")
        )
    return items
