# -*- coding: utf-8 -*-
"""基于 Python Web 的课堂专注度分析系统 —— 全局配置模块。

本模块集中保存系统运行所需的全部可调参数：

* 目录结构（模型、上传、结果、模板、静态资源）
* YOLOv8 课堂行为检测参数（模型路径、置信度、IoU、推理尺寸、设备）
* 6 类课堂行为定义与中文名称（与原 class_Detection_end 项目保持一致）
* 课堂专注度算法的行为权重与评价区间
* 数据库连接（默认 MySQL，连接失败时自动回退 SQLite，便于演示与测试）
* 登录认证参数（JWT 密钥、有效期、Cookie 名称）
* 视频检测 / 实时检测的采样与落库间隔

所有参数均支持通过环境变量或项目根目录下的 ``.env`` 文件覆盖，
避免在业务代码中硬编码，便于论文中统一说明系统配置。
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 基础路径
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

try:  # 可选依赖：读取 .env，便于在不同机器上切换数据库 / 模型路径
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:  # pragma: no cover - dotenv 缺失时不影响系统运行
    pass


def _get_str(key: str, default: str) -> str:
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return int(default)


def _get_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return float(default)


def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# 目录定义
# ---------------------------------------------------------------------------
MODELS_DIR = BASE_DIR / "models"
UPLOAD_DIR = Path(_get_str("CLASSROOM_UPLOAD_DIR", str(BASE_DIR / "uploads")))
RESULT_DIR = Path(_get_str("CLASSROOM_RESULT_DIR", str(BASE_DIR / "results")))
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
LOG_DIR = BASE_DIR / "logs"
DATASET_DIR = BASE_DIR / "datasets" / "dataset"
TRAINING_DIR = BASE_DIR / "training"

for _directory in (UPLOAD_DIR, RESULT_DIR, LOG_DIR, STATIC_DIR, TEMPLATE_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# YOLOv8 课堂行为检测参数
# ---------------------------------------------------------------------------
# 主模型：由原项目 runs/v8-4-pose-all2/weights/best.pt（6 类课堂行为）复制而来
MODEL_PATH = Path(_get_str("CLASSROOM_MODEL_PATH", str(MODELS_DIR / "classroom_behavior.pt")))
# 备用权重：按顺序查找，主模型缺失时自动使用（训练输出目录中的原始 best.pt）
MODEL_FALLBACK_PATHS: tuple[Path, ...] = tuple(
    Path(item)
    for item in _get_str(
        "CLASSROOM_MODEL_FALLBACKS",
        str(BASE_DIR / "runs" / "v8-4-pose-all2" / "weights" / "best.pt"),
    ).split(";")
    if item.strip()
)

# 检测置信度阈值 / NMS IoU 阈值 / 推理尺寸 / 单帧最大目标数
CONF_THRESHOLD = _get_float("CLASSROOM_CONF", 0.25)
IOU_THRESHOLD = _get_float("CLASSROOM_IOU", 0.45)
IMAGE_SIZE = _get_int("CLASSROOM_IMGSZ", 640)
MAX_DETECTIONS = _get_int("CLASSROOM_MAX_DET", 300)
# auto：由 ultralytics 自动选择 CUDA / CPU；也可写 cpu、cuda:0
DEVICE = _get_str("CLASSROOM_DEVICE", "auto")

# ---------------------------------------------------------------------------
# 课堂行为类别定义（与原项目 data.yaml 完全一致）
# ---------------------------------------------------------------------------
# 类别英文名
CLASS_NAMES: dict[int, str] = {
    0: "hand-raising",
    1: "reading",
    2: "writing",
    3: "using phone",
    4: "bowing the head",
    5: "leaning over the table",
}

# 类别中文名
CLASS_NAMES_CN: dict[int, str] = {
    0: "举手",
    1: "阅读",
    2: "写作",
    3: "使用手机",
    4: "低头",
    5: "靠在桌上",
}

# 行为在 JSON / 数据库 / 前端中使用的统一英文键（Web 接口命名风格）
BEHAVIOR_KEYS: dict[int, str] = {
    0: "hand_raising",
    1: "reading",
    2: "writing",
    3: "using_phone",
    4: "bowing_head",
    5: "leaning_over_table",
}

# 行为键与中文名、英文名的对照表（用于统计、报告、图表）
BEHAVIOR_LABELS: dict[str, dict[str, str]] = {
    BEHAVIOR_KEYS[i]: {"cn": CLASS_NAMES_CN[i], "en": CLASS_NAMES[i]}
    for i in CLASS_NAMES
}

# 图表 / 统计展示顺序
BEHAVIOR_ORDER: list[str] = [BEHAVIOR_KEYS[i] for i in sorted(BEHAVIOR_KEYS)]

# 名称归一化别名：兼容不同数据集 / 模型导出的写法
BEHAVIOR_ALIASES: dict[str, str] = {
    "hand_raising": "hand_raising",
    "handraising": "hand_raising",
    "hand-raising": "hand_raising",
    "raising_hand": "hand_raising",
    "hand raise": "hand_raising",
    "raising hand": "hand_raising",
    "reading": "reading",
    "writing": "writing",
    "using_phone": "using_phone",
    "usingphone": "using_phone",
    "using phone": "using_phone",
    "using-phone": "using_phone",
    "phone": "using_phone",
    "bowing_head": "bowing_head",
    "bowingthehead": "bowing_head",
    "bowing the head": "bowing_head",
    "bowing-head": "bowing_head",
    "head_down": "bowing_head",
    "leaning_over_table": "leaning_over_table",
    "leaningoverthetable": "leaning_over_table",
    "leaning over the table": "leaning_over_table",
    "leaning-over-the-table": "leaning_over_table",
    "leaning_on_the_table": "leaning_over_table",
}

# ---------------------------------------------------------------------------
# 课堂专注度算法参数
# ---------------------------------------------------------------------------
# 行为专注度权重（系统设计初始参数，需通过实验 / 专家意见验证，并非通用标准）
ATTENTION_WEIGHTS: dict[str, float] = {
    "hand_raising": 1.0,          # 举手：积极参与课堂
    "reading": 1.0,               # 阅读：专注学习行为
    "writing": 1.0,               # 写作：专注学习行为
    "using_phone": 0.0,           # 使用手机：完全非专注
    "bowing_head": 0.3,           # 低头：可能走神
    "leaning_over_table": 0.2,    # 趴桌 / 靠桌：接近睡眠状态
}

# 专注 / 非专注行为的划分（用于统计专注人数与不专注人数）
FOCUSED_BEHAVIORS: tuple[str, ...] = ("hand_raising", "reading", "writing")
UNFOCUSED_BEHAVIORS: tuple[str, ...] = ("using_phone", "bowing_head", "leaning_over_table")

# 专注度评价区间：(下限, 评价)，按从高到低匹配
ATTENTION_LEVELS: list[tuple[float, str]] = [
    (90.0, "非常专注"),
    (80.0, "比较专注"),
    (70.0, "中等水平"),
    (60.0, "偏低"),
    (0.0, "不专注"),
]

# 专注度区间统计（报告中的区间分布图）
ATTENTION_BUCKETS: list[tuple[float, float, str]] = [
    (0.0, 60.0, "0-60%"),
    (60.0, 70.0, "60-70%"),
    (70.0, 80.0, "70-80%"),
    (80.0, 90.0, "80-90%"),
    (90.0, 100.0, "90-100%"),
]

# ---------------------------------------------------------------------------
# 数据库配置
# ---------------------------------------------------------------------------
# 数据库名称：class_detection（MySQL 8.0 / utf8mb4）
DB_NAME = _get_str("CLASSROOM_DB_NAME", "class_detection")
# 不在代码中内置任何数据库地址与密码，必须通过项目根目录的 .env 配置：
#     CLASSROOM_DB_URL=mysql+pymysql://root:<PASSWORD>@127.0.0.1:3306/class_detection?charset=utf8mb4
DB_URL = _get_str("CLASSROOM_DB_URL", "")
SQLITE_PATH = BASE_DIR / _get_str("CLASSROOM_SQLITE_FILE", "classroom_attention.db")
# 是否允许 MySQL 连接失败后回退 SQLite。
# 正式运行应为 False（确保系统真正使用 MySQL）；仅在本机无 MySQL 的开发场合才打开。
DB_SQLITE_FALLBACK = _get_bool("CLASSROOM_SQLITE_FALLBACK", False)
DB_ECHO = _get_bool("CLASSROOM_DB_ECHO", False)
DB_CONNECT_TIMEOUT = _get_int("CLASSROOM_DB_TIMEOUT", 4)

# 是否在启动时创建默认管理员账号
CREATE_DEFAULT_ADMIN = _get_bool("CLASSROOM_CREATE_ADMIN", True)
DEFAULT_ADMIN = {
    "username": _get_str("CLASSROOM_ADMIN_USER", "admin"),
    "password": _get_str("CLASSROOM_ADMIN_PASSWORD", "admin123"),
    "real_name": _get_str("CLASSROOM_ADMIN_NAME", "系统管理员"),
    "role": "admin",
}

# ---------------------------------------------------------------------------
# 登录认证配置
# ---------------------------------------------------------------------------
SECRET_KEY = _get_str("CLASSROOM_SECRET_KEY", "classroom-attention-secret-key-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = _get_int("CLASSROOM_TOKEN_EXPIRE_MINUTES", 12 * 60)
# 登录页"记住密码"（实现为记住登录状态）：勾选后登录有效期延长
REMEMBER_ME_EXPIRE_MINUTES = _get_int("CLASSROOM_REMEMBER_EXPIRE_MINUTES", 30 * 24 * 60)
COOKIE_NAME = "classroom_token"
ROLES = {"admin": "管理员", "teacher": "教师"}
# 账号状态：1 正常 / 0 已禁用
USER_STATUS = {1: "正常", 0: "已禁用"}
# 登录失败次数限制（防止暴力破解）
LOGIN_MAX_ATTEMPTS = _get_int("CLASSROOM_LOGIN_MAX_ATTEMPTS", 5)
LOGIN_LOCK_SECONDS = _get_int("CLASSROOM_LOGIN_LOCK_SECONDS", 300)

# ---------------------------------------------------------------------------
# 检测任务与实时检测配置
# ---------------------------------------------------------------------------
UPLOAD_MAX_MB = _get_int("CLASSROOM_UPLOAD_MAX_MB", 200)
# 视频检测：每隔多少帧做一次 YOLOv8 推理
VIDEO_SAMPLE_INTERVAL = _get_int("CLASSROOM_VIDEO_INTERVAL", 5)
# 视频检测：每隔多少秒写入一次数据库（避免写入过于频繁）
VIDEO_RECORD_INTERVAL = _get_float("CLASSROOM_VIDEO_RECORD_INTERVAL", 5.0)
# 实时检测：每隔多少秒写入一次数据库
REALTIME_RECORD_INTERVAL = _get_float("CLASSROOM_REALTIME_RECORD_INTERVAL", 5.0)
# 实时检测：浏览器上传帧的最大边长（超过则缩小，降低带宽与推理开销）
REALTIME_MAX_SIDE = _get_int("CLASSROOM_REALTIME_MAX_SIDE", 960)
# 实时检测：返回给浏览器的标注画面 JPEG 质量
REALTIME_JPEG_QUALITY = _get_int("CLASSROOM_REALTIME_JPEG_QUALITY", 70)
# 服务器端摄像头实时检测时的采样间隔（秒）
REALTIME_CAMERA_INTERVAL = _get_float("CLASSROOM_CAMERA_INTERVAL", 0.2)

ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"}

# ---------------------------------------------------------------------------
# 服务器启动参数
# ---------------------------------------------------------------------------
SERVER_HOST = _get_str("CLASSROOM_HOST", "127.0.0.1")
SERVER_PORT = _get_int("CLASSROOM_PORT", 8000)


def attention_weights() -> dict[str, float]:
    """返回当前生效的行为专注度权重（副本）。"""
    return dict(ATTENTION_WEIGHTS)


def behavior_cn(key: str) -> str:
    """行为英文键 -> 中文名称。"""
    return BEHAVIOR_LABELS.get(key, {}).get("cn", key)


def behavior_en(key: str) -> str:
    """行为英文键 -> 模型英文类别名。"""
    return BEHAVIOR_LABELS.get(key, {}).get("en", key)


def config_snapshot() -> dict:
    """汇总当前配置，供 /api/system/status 与管理页面展示。"""
    return {
        "database_name": DB_NAME,
        "model_path": str(MODEL_PATH),
        "model_exists": MODEL_PATH.exists(),
        "model_fallbacks": [str(item) for item in MODEL_FALLBACK_PATHS],
        "conf_threshold": CONF_THRESHOLD,
        "iou_threshold": IOU_THRESHOLD,
        "image_size": IMAGE_SIZE,
        "device": DEVICE,
        "classes": {str(k): v for k, v in CLASS_NAMES.items()},
        "classes_cn": {str(k): v for k, v in CLASS_NAMES_CN.items()},
        "attention_weights": ATTENTION_WEIGHTS,
        "remember_me_expire_minutes": REMEMBER_ME_EXPIRE_MINUTES,
        "login_max_attempts": LOGIN_MAX_ATTEMPTS,
        "video_sample_interval": VIDEO_SAMPLE_INTERVAL,
        "realtime_record_interval": REALTIME_RECORD_INTERVAL,
    }
