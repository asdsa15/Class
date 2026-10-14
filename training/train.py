# -*- coding: utf-8 -*-
"""YOLOv8 课堂行为检测模型训练脚本（模型训练模块，非 Web 运行时核心代码）。

本脚本由原项目根目录的 ``train.py`` 整理而来，主要改动：

1. 数据集路径不再硬编码 ``E:/00code/...``，改为读取同目录下的
   ``data.yaml``，并在训练前自动把相对路径解析为绝对路径；
2. 训练超参数（epochs / batch / imgsz / 预训练权重等）统一配置在本文件顶部，
   避免大量硬编码；
3. 训练结果默认输出到 ``runs/detect`` 目录，与原项目保持一致。

用法::

    python training/train.py

"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from ultralytics import YOLO

# ---------------------------------------------------------------------------
# 训练参数统一配置
# ---------------------------------------------------------------------------
DATA_YAML = Path(__file__).resolve().parent / "data.yaml"
# 预训练权重：优先使用项目根目录的 yolov8n.pt，缺失时由 ultralytics 自动下载
PRETRAINED = PROJECT_ROOT / "yolov8n.pt"
EPOCHS = 250
BATCH = 4
IMAGE_SIZE = 640
WORKERS = 4
PROJECT = str(PROJECT_ROOT / "runs" / "detect")
NAME = "classroom-behavior"
DEVICE = None          # None 表示自动选择；也可写 0（GPU）或 "cpu"
RESUME = False
SEED = 0


def resolve_data_yaml(source: Path = DATA_YAML) -> Path:
    """把 data.yaml 中的相对路径解析为绝对路径，生成临时配置文件。

    Ultralytics 会把 ``path`` 字段当作相对其全局 datasets 目录的路径处理，
    这里显式转换为绝对路径，保证训练在任意盘符、任意机器上都能找到数据集。
    """
    with open(source, "r", encoding="utf-8") as fp:
        config = yaml.safe_load(fp)

    dataset_dir = (source.parent / str(config.get("path", "."))).resolve()
    if not dataset_dir.exists():
        raise FileNotFoundError(f"数据集目录不存在：{dataset_dir}")

    config["path"] = str(dataset_dir)
    resolved = source.with_name("data_resolved.yaml")
    with open(resolved, "w", encoding="utf-8") as fp:
        yaml.safe_dump(config, fp, allow_unicode=True, sort_keys=False)
    print(f"[信息] 数据集根目录：{dataset_dir}")
    print(f"[信息] 已生成绝对路径配置：{resolved}")
    return resolved


def main() -> None:
    data_yaml = resolve_data_yaml()
    model = YOLO(str(PRETRAINED) if PRETRAINED.exists() else "yolov8n.pt")

    model.train(
        data=str(data_yaml),
        epochs=EPOCHS,
        batch=BATCH,
        imgsz=IMAGE_SIZE,
        workers=WORKERS,
        device=DEVICE,
        project=PROJECT,
        name=NAME,
        resume=RESUME,
        seed=SEED,
    )

    # 训练完成后可直接导出 ONNX（按论文需要选择是否启用）
    # model.export(format="onnx")

    metrics = model.val(data=str(data_yaml), split="test", imgsz=IMAGE_SIZE, batch=BATCH)
    print("[信息] 测试集评估结果：")
    print(metrics)


if __name__ == "__main__":
    main()
