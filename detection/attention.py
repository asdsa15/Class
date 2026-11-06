# -*- coding: utf-8 -*-
"""课堂专注度计算模块（对应修改报告第 18、19 节）。

这是新系统相对原 PyQt5 项目最重要的新增能力：

    行为检测 -> 行为分类 -> 行为数量统计 -> 专注度权重 -> 专注度计算

计算公式（加权平均）::

        A = Σ(N_i × W_i) / Σ(N_i) × 100%

其中 N_i 为第 i 类行为的人数，W_i 为该行为的专注度权重，A 为课堂专注度。
权重属于系统设计的初始参数，正式论文中应通过实验或专家意见进行验证说明，
不宜宣称其为通用标准。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import config


def attention_level(score: float | None) -> str:
    """根据专注度数值返回评价等级文字。"""
    if score is None:
        return "无有效数据"
    for threshold, label in config.ATTENTION_LEVELS:
        if score >= threshold:
            return label
    return config.ATTENTION_LEVELS[-1][1]


@dataclass
class AttentionResult:
    """课堂专注度计算结果。"""

    score: float | None
    student_count: int
    focused_count: int
    unfocused_count: int
    weighted_sum: float
    contributions: dict[str, dict[str, Any]] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    # 检测覆盖率相关：检出人数、应到人数与覆盖率（%），用于说明结果的可靠性
    detected_students: int = 0
    expected_students: int = 0
    coverage: float = 0.0

    @property
    def level(self) -> str:
        return attention_level(self.score)

    @property
    def coverage_warning(self) -> str:
        """检测覆盖率不足时的提示文字（覆盖率达到阈值则为空串）。"""
        if self.expected_students <= 0:
            return ""
        if self.coverage < 60.0:
            return (
                f"检测覆盖率仅 {self.coverage:.1f}%（检出 {self.detected_students} 人 / "
                f"应到 {self.expected_students} 人），专注度结果仅供参考"
            )
        return ""

    @property
    def focused_ratio(self) -> float:
        """专注人数占比（%）。"""
        if not self.student_count:
            return 0.0
        return round(self.focused_count / self.student_count * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level,
            "student_count": self.student_count,
            "focused_count": self.focused_count,
            "unfocused_count": self.unfocused_count,
            "focused_ratio": self.focused_ratio,
            "weighted_sum": round(self.weighted_sum, 3),
            "weights": self.weights,
            "contributions": self.contributions,
            "detected_students": self.detected_students,
            "expected_students": self.expected_students,
            "coverage": self.coverage,
            "coverage_warning": self.coverage_warning,
            "formula": "A = Σ(N_i × W_i) / max(应到人数, 检出人数) × 100%",
        }


def calculate_attention(
    counts: Mapping[str, int] | Iterable[Any],
    weights: Mapping[str, float] | None = None,
    expected_students: int | None = None,
) -> AttentionResult:
    """计算课堂专注度。

    :param counts: 行为数量字典，或直接传入检测结果列表；
    :param weights: 行为权重，缺省使用 config.ATTENTION_WEIGHTS；
    :param expected_students: 班级应到人数。若给出且大于检出人数，
        则以应到人数作为分母，使专注度反映"全班"水平而不是"被检出者"水平；
        0 或 None 表示未知，仍按检出人数计算（兼容原有行为）。
    :return: AttentionResult；未检测到学生时 score 为 None。
    """
    if not isinstance(counts, Mapping):
        from detection.behavior import summarize_detections

        counts = summarize_detections(counts).counts

    active_weights = dict(weights or config.ATTENTION_WEIGHTS)
    contributions: dict[str, dict[str, Any]] = {}
    weighted_sum = 0.0
    total_students = 0
    focused_count = 0
    unfocused_count = 0

    keys = list(config.BEHAVIOR_ORDER)
    for key in counts:
        if key not in keys:
            keys.append(key)

    for key in keys:
        count = int(counts.get(key, 0) or 0)
        weight = float(active_weights.get(key, 0.0))
        contribution = count * weight
        weighted_sum += contribution
        total_students += count
        if key in config.FOCUSED_BEHAVIORS:
            focused_count += count
        elif key in config.UNFOCUSED_BEHAVIORS:
            unfocused_count += count
        contributions[key] = {
            "name_cn": config.behavior_cn(key),
            "count": count,
            "weight": weight,
            "contribution": round(contribution, 3),
        }

    # 分母口径：优先使用班级应到人数，让专注度反映全班水平；
    # 应到人数未知（0/None）或小于检出人数（数据异常）时回退到检出人数。
    capacity = int(expected_students or 0)
    denominator = capacity if capacity > total_students else total_students
    coverage = round(total_students / denominator * 100, 2) if denominator else 0.0
    score = round(weighted_sum / denominator * 100, 2) if denominator else None

    return AttentionResult(
        score=score,
        student_count=denominator,
        focused_count=focused_count,
        unfocused_count=unfocused_count,
        weighted_sum=weighted_sum,
        contributions=contributions,
        weights=active_weights,
        detected_students=total_students,
        expected_students=capacity,
        coverage=coverage,
    )


def aggregate_scores(scores: Sequence[float]) -> dict[str, Any]:
    """统计一段课堂中专注度序列的平均值 / 最高值 / 最低值。"""
    values = [float(s) for s in scores if s is not None]
    if not values:
        return {
            "avg_attention": None,
            "max_attention": None,
            "min_attention": None,
            "record_count": 0,
            "level": "无有效数据",
        }
    average = round(sum(values) / len(values), 2)
    return {
        "avg_attention": average,
        "max_attention": round(max(values), 2),
        "min_attention": round(min(values), 2),
        "record_count": len(values),
        "level": attention_level(average),
    }


def bucket_distribution(scores: Sequence[float]) -> list[dict[str, Any]]:
    """把专注度序列划分到若干区间（用于报告中的专注度区间分布统计）。"""
    values = [float(s) for s in scores if s is not None]
    total = len(values)
    result = []
    for low, high, label in config.ATTENTION_BUCKETS:
        if high >= 100:
            count = sum(1 for value in values if low <= value <= high)
        else:
            count = sum(1 for value in values if low <= value < high)
        result.append(
            {
                "label": label,
                "count": count,
                "ratio": round(count / total * 100, 2) if total else 0.0,
            }
        )
    return result
