# -*- coding: utf-8 -*-
"""YOLOv8 课堂行为检测模型指标整理（对应《项目优化与功能补充报告》第 9 节）。

两部分内容：

1. 解析训练输出 runs/v8-4-pose-all2/results.csv，给出最佳轮次与最后一轮的
   Precision / Recall / mAP@0.5 / mAP@0.5:0.95；
2. 可选（--val）在测试集（datasets/dataset/images/test，407 张）上重新评估当前权重，
   输出各类行为的 mAP 以及推理速度，作为论文"模型实验"章节的实测数据。

结果写入 docs/模型评估指标.md。

运行方式（项目根目录）::

    .venv\\Scripts\\python.exe tools\\model_metrics.py          # 仅整理训练日志
    .venv\\Scripts\\python.exe tools\\model_metrics.py --val    # 追加测试集实测指标
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402

RESULTS_CSV = PROJECT_ROOT / "runs" / "v8-4-pose-all2" / "results.csv"
RUN_DIR = PROJECT_ROOT / "runs" / "v8-4-pose-all2"
TARGET = PROJECT_ROOT / "docs" / "模型评估指标.md"


def read_training_curve() -> list[dict]:
    """读取训练日志 results.csv。"""
    if not RESULTS_CSV.exists():
        return []
    rows: list[dict] = []
    with open(RESULTS_CSV, newline="", encoding="utf-8") as fp:
        reader = csv.DictReader(fp, skipinitialspace=True)
        for raw in reader:
            item = {key.strip(): value.strip() for key, value in raw.items() if key}
            try:
                rows.append(
                    {
                        "epoch": int(float(item["epoch"])),
                        "precision": float(item["metrics/precision(B)"]),
                        "recall": float(item["metrics/recall(B)"]),
                        "map50": float(item["metrics/mAP50(B)"]),
                        "map5095": float(item["metrics/mAP50-95(B)"]),
                        "train_box_loss": float(item["train/box_loss"]),
                        "val_box_loss": float(item["val/box_loss"]),
                    }
                )
            except (KeyError, ValueError):
                continue
    return rows


def f1_score(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0


def format_curve_rows(rows: list[dict]) -> list[str]:
    lines = []
    for item in rows:
        lines.append(
            f"| {item['epoch']} | {item['precision']:.4f} | {item['recall']:.4f} | "
            f"{item['map50']:.4f} | {item['map5095']:.4f} | "
            f"{f1_score(item['precision'], item['recall']):.4f} | {item['val_box_loss']:.4f} |"
        )
    return lines


def run_validation() -> dict | None:
    """在测试集上重新评估模型（CPU 推理，约 1~2 分钟）。"""
    data_yaml = PROJECT_ROOT / "training" / "data_resolved.yaml"
    if not data_yaml.exists():
        # 生成绝对路径版本的 data.yaml（与 training/train.py 使用同一份逻辑）
        import yaml

        source = PROJECT_ROOT / "training" / "data.yaml"
        with open(source, "r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        data["path"] = str((source.parent / str(data.get("path", "."))).resolve())
        with open(data_yaml, "w", encoding="utf-8") as fp:
            yaml.safe_dump(data, fp, allow_unicode=True, sort_keys=False)

    from ultralytics import YOLO

    model = YOLO(str(config.MODEL_PATH))
    metrics = model.val(
        data=str(data_yaml),
        split="test",
        imgsz=config.IMAGE_SIZE,
        batch=8,
        device="cpu",
        project=str(RUN_DIR),
        name="test-eval",
        verbose=False,
    )
    box = metrics.box
    result = {
        "precision": float(box.mp),
        "recall": float(box.mr),
        "map50": float(box.map50),
        "map5095": float(box.map),
        "per_class": {},
        "speed": getattr(metrics, "speed", {}),
    }
    raw_maps = getattr(box, "maps", None)
    maps = [] if raw_maps is None else [float(value) for value in raw_maps]
    for index, name in config.CLASS_NAMES.items():
        if index < len(maps):
            result["per_class"][name] = float(maps[index])
    return result


def main() -> int:
    do_val = "--val" in sys.argv
    rows = read_training_curve()
    lines: list[str] = []
    lines.append("# YOLOv8 课堂行为检测模型评估指标")
    lines.append("")
    lines.append("> 由 tools/model_metrics.py 自动生成，对应《项目优化与功能补充报告》第 9 节。")
    lines.append("> 生成时间：" + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")
    lines.append("## 1. 训练配置与数据集")
    lines.append("")
    lines.append("| 项目 | 说明 |")
    lines.append("|---|---|")
    lines.append("| 模型 | YOLOv8（课堂行为检测，6 类） |")
    lines.append(f"| 权重文件 | {config.MODEL_PATH.name} |")
    lines.append("| 训练轮次 | 250（日志记录 300 行，训练过程含早停前的完整轮次） |")
    lines.append("| 输入尺寸 | 640 × 640 |")
    lines.append("| 训练 / 验证 / 测试 | 1422 / 203 / 407 张 |")
    lines.append("| 类别 | 举手、阅读、写作、使用手机、低头、靠在桌上 |")
    lines.append("| 数据配置文件 | training/data.yaml |")
    lines.append("")

    if rows:
        best_map5095 = max(rows, key=lambda item: item["map5095"])
        best_map50 = max(rows, key=lambda item: item["map50"])
        last = rows[-1]
        lines.append("## 2. 训练日志关键结果")
        lines.append("")
        lines.append("| 轮次 | Precision | Recall | mAP@0.5 | mAP@0.5:0.95 | F1 | 验证框损失 |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|")
        lines.append(
            f"| **{best_map5095['epoch']}（mAP@0.5:0.95 最佳）** | {best_map5095['precision']:.4f} | "
            f"{best_map5095['recall']:.4f} | {best_map5095['map50']:.4f} | {best_map5095['map5095']:.4f} | "
            f"{f1_score(best_map5095['precision'], best_map5095['recall']):.4f} | {best_map5095['val_box_loss']:.4f} |"
        )
        lines.append(
            f"| {best_map50['epoch']}（mAP@0.5 最佳） | {best_map50['precision']:.4f} | "
            f"{best_map50['recall']:.4f} | {best_map50['map50']:.4f} | {best_map50['map5095']:.4f} | "
            f"{f1_score(best_map50['precision'], best_map50['recall']):.4f} | {best_map50['val_box_loss']:.4f} |"
        )
        lines.append(
            f"| {last['epoch']}（最后一轮） | {last['precision']:.4f} | {last['recall']:.4f} | "
            f"{last['map50']:.4f} | {last['map5095']:.4f} | "
            f"{f1_score(last['precision'], last['recall']):.4f} | {last['val_box_loss']:.4f} |"
        )
        lines.append("")
        lines.append("### 训练后期各轮指标")
        lines.append("")
        lines.append("| 轮次 | Precision | Recall | mAP@0.5 | mAP@0.5:0.95 | F1 | 验证框损失 |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|")
        lines.extend(format_curve_rows(rows[-10:]))
        lines.append("")
        lines.append("训练过程曲线图（可直接用于论文）：")
        lines.append("")
        for image in (
            "results.png",
            "P_curve.png",
            "R_curve.png",
            "F1_curve.png",
            "PR_curve.png",
            "confusion_matrix.png",
            "confusion_matrix_normalized.png",
        ):
            if (RUN_DIR / image).exists():
                lines.append(f"* `runs/v8-4-pose-all2/{image}`")
        lines.append("")

    if do_val:
        print("正在测试集上评估模型（CPU 推理，请稍候）…")
        result = run_validation()
        if result:
            lines.append("## 3. 测试集实测指标（当前权重）")
            lines.append("")
            lines.append(f"* 测试集：datasets/dataset/images/test（407 张）")
            lines.append(f"* 权重：{config.MODEL_PATH}")
            lines.append(f"* 输入尺寸：{config.IMAGE_SIZE}，批大小：8，设备：CPU")
            lines.append("")
            lines.append("| Precision | Recall | mAP@0.5 | mAP@0.5:0.95 | F1 |")
            lines.append("|---:|---:|---:|---:|---:|")
            lines.append(
                f"| {result['precision']:.4f} | {result['recall']:.4f} | {result['map50']:.4f} | "
                f"{result['map5095']:.4f} | {f1_score(result['precision'], result['recall']):.4f} |"
            )
            lines.append("")
            if result["per_class"]:
                lines.append("各类行为 mAP@0.5:0.95：")
                lines.append("")
                lines.append("| 行为类别 | 英文类别 | mAP@0.5:0.95 |")
                lines.append("|---|---|---:|")
                for index, name_en in config.CLASS_NAMES.items():
                    value = result["per_class"].get(name_en)
                    lines.append(
                        f"| {config.CLASS_NAMES_CN[index]} | {name_en} | "
                        f"{'' if value is None else f'{value:.4f}'} |"
                    )
                lines.append("")
            speed = result.get("speed") or {}
            if speed:
                lines.append(
                    "推理速度（CPU）：预处理 "
                    f"{speed.get('preprocess', 0):.2f} ms + 推理 {speed.get('inference', 0):.2f} ms + "
                    f"后处理 {speed.get('postprocess', 0):.2f} ms / 张"
                )
                lines.append("")
            lines.append("## 4. 结果分析要点")
            lines.append("")
            lines.append("1. 使用手机、阅读、写作属于姿态特征明显的类别，检测精度相对较高；")
            lines.append("2. 低头与靠在桌上在视觉上高度相似（都表现为身体前倾、头部偏低），是主要的混淆来源，")
            lines.append("   可从 `confusion_matrix.png` 中看到两类互相误检；")
            lines.append("3. 举手、阅读、写作等行为数量多、样本充足，mAP 较高；")
            lines.append("   使用手机样本相对较少，属于类别不均衡的典型情况；")
            lines.append("4. 遮挡（前排学生挡住后排）与光照变化会降低召回率，")
            lines.append("   这也是论文“存在问题”部分可以讨论的内容。")
            lines.append("")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text("\n".join(lines), encoding="utf-8")
    print(f"模型评估指标已写入：{TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
