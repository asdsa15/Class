# -*- coding: utf-8 -*-
"""图像处理工具（由原项目 detect_tools.py 抽取重构）。

原 detect_tools.py 中同时包含大量 PyQt5 界面相关代码
（cvimg_to_qpiximg、cv_show、save_video 等），Web 系统中不再需要；
这里只保留与 YOLOv8 检测、图像读写、检测框绘制有关的函数，
并补充 base64 编解码，供 HTTP 接口与 WebSocket 实时检测复用。
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config

# ---------------------------------------------------------------------------
# 颜色（沿用原项目 detect_tools.py 的调色板，保证与原桌面版视觉效果一致）
# ---------------------------------------------------------------------------
_HEX_PALETTE = (
    "FF3838", "FF9D97", "FF701F", "FFB21D", "CFD231", "48F90A", "92CC17",
    "3DDB86", "1A9334", "00D4BB", "2C99A8", "00C2FF", "344593", "6473FF",
    "0018EC", "8438FF", "520085", "CB38FF", "FF95C8", "FF37C7",
)


class Colors:
    """用于为不同行为类别分配稳定的颜色。"""

    def __init__(self) -> None:
        self.palette = [self.hex2rgb(f"#{c}") for c in _HEX_PALETTE]
        self.n = len(self.palette)

    def __call__(self, index: int, bgr: bool = False) -> tuple[int, int, int]:
        color = self.palette[int(index) % self.n]
        return (color[2], color[1], color[0]) if bgr else color

    @staticmethod
    def hex2rgb(value: str) -> tuple[int, int, int]:
        return tuple(int(value[1 + i: 1 + i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


COLORS = Colors()

# ---------------------------------------------------------------------------
# 中文字体：优先使用项目自带字体，其次使用 Windows 常见中文字体
# ---------------------------------------------------------------------------
_FONT_CANDIDATES = (
    config.BASE_DIR / "Font" / "platech.ttf",
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/simsun.ttc"),
)
_FONT_CACHE: dict[int, ImageFont.FreeTypeFont | None] = {}


def load_font(size: int = 18) -> ImageFont.FreeTypeFont | None:
    """加载中文字体，失败时返回 None（此时退化为英文标签）。"""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    font: ImageFont.FreeTypeFont | None = None
    for candidate in _FONT_CANDIDATES:
        try:
            if candidate.exists():
                font = ImageFont.truetype(str(candidate), size)
                break
        except Exception:
            continue
    _FONT_CACHE[size] = font
    return font


# ---------------------------------------------------------------------------
# 图像读写（兼容中文路径，沿用原项目 img_cvread 的做法）
# ---------------------------------------------------------------------------
def imread(path: str | Path) -> np.ndarray | None:
    """读取图片，支持中文 / 空格路径。"""
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        return image
    except Exception:
        return None


def imwrite(path: str | Path, image: np.ndarray, quality: int = 95) -> bool:
    """保存图片，支持中文 / 空格路径。"""
    suffix = Path(path).suffix.lower() or ".jpg"
    params = [int(cv2.IMWRITE_JPEG_QUALITY), quality] if suffix in {".jpg", ".jpeg"} else []
    try:
        ok, buffer = cv2.imencode(suffix, image, params)
        if not ok:
            return False
        buffer.tofile(str(path))
        return True
    except Exception:
        return False


def resize_max_side(image: np.ndarray, max_side: int) -> np.ndarray:
    """按最长边等比缩放图像（不放大），用于降低实时检测的开销。"""
    height, width = image.shape[:2]
    longest = max(height, width)
    if max_side <= 0 or longest <= max_side:
        return image
    scale = max_side / float(longest)
    return cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------
# base64 / 字节流编解码（HTTP 接口与 WebSocket 复用）
# ---------------------------------------------------------------------------
def encode_jpeg(image: np.ndarray, quality: int = 80) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("图像编码失败")
    return buffer.tobytes()


def encode_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("图像编码失败")
    return buffer.tobytes()


def bgr_to_base64(image: np.ndarray, quality: int = 80, mime: str = "image/jpeg") -> str:
    """OpenCV 图像 -> data URI 字符串，可直接用于前端 img 标签。"""
    data = encode_jpeg(image, quality) if mime == "image/jpeg" else encode_png(image)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def base64_to_bgr(text: str) -> np.ndarray | None:
    """data URI 或纯 base64 字符串 -> OpenCV 图像。"""
    if not text:
        return None
    if "," in text and text.strip().lower().startswith("data:"):
        text = text.split(",", 1)[1]
    try:
        raw = base64.b64decode(text)
    except Exception:
        return None
    return decode_image_bytes(raw)


def decode_image_bytes(data: bytes) -> np.ndarray | None:
    """二进制图片数据 -> OpenCV 图像。"""
    try:
        buffer = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception:
        return None


def image_to_bytes(image: np.ndarray, fmt: str = "JPEG") -> bytes:
    """PIL 方式编码，供需要文件流的场景使用。"""
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    stream = io.BytesIO()
    pil_image.save(stream, format=fmt)
    return stream.getvalue()


# ---------------------------------------------------------------------------
# 检测框绘制
# ---------------------------------------------------------------------------
def draw_detections(
    image: np.ndarray,
    detections: Iterable[dict],
    show_confidence: bool = True,
    show_cn: bool = True,
    thickness: int = 2,
    font_size: int = 18,
) -> np.ndarray:
    """在图像上绘制检测框与中文标签。

    detections 中的每一项需包含 ``xyxy``、``behavior_key``、``confidence`` 字段，
    通常直接传入 :meth:`detection.detector.Detection.to_dict` 的结果。
    """
    canvas = image.copy()
    items = list(detections)
    if not items:
        return canvas

    font = load_font(font_size)
    texts: list[tuple[tuple[int, int], str, tuple[int, int, int]]] = []

    for item in items:
        x1, y1, x2, y2 = (int(round(v)) for v in item["xyxy"])
        key = item.get("behavior_key") or config.BEHAVIOR_KEYS.get(int(item.get("class_id", 0)), "")
        color = COLORS(int(item.get("class_id", 0)), bgr=True)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)

        label = config.behavior_cn(key) if show_cn else config.behavior_en(key)
        if show_confidence:
            label = f"{label} {float(item.get('confidence', 0.0)) * 100:.0f}%"

        # 标签背景
        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        label_w = text_size[0] + 8
        label_h = font_size + 8 if font else text_size[1] + 8
        top = max(y1 - label_h, 0)
        cv2.rectangle(canvas, (x1, top), (x1 + label_w, top + label_h), color, -1)
        texts.append(((x1 + 4, top + 3), label, color))

    if font is None:
        for (x, y), label, color in texts:
            cv2.putText(
                canvas, label, (x, y + font_size - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
            )
        return canvas

    pil_image = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)
    for position, label, _color in texts:
        draw.text(position, label, fill=(255, 255, 255), font=font)
    return cv2.cvtColor(np.asarray(pil_image), cv2.COLOR_RGB2BGR)


def draw_hud(
    image: np.ndarray,
    lines: Sequence[str],
    position: str = "top-left",
    font_size: int = 22,
) -> np.ndarray:
    """在图像上叠加半透明信息面板（实时课堂画面左上角的专注度 HUD）。"""
    if not lines:
        return image
    canvas = image.copy()
    height, width = canvas.shape[:2]
    line_height = font_size + 12
    panel_w = min(width - 20, max(260, int(width * 0.34)))
    panel_h = line_height * len(lines) + 16
    x0 = 10 if position.startswith("top-left") else max(width - panel_w - 10, 10)
    y0 = 10

    overlay = canvas.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), (24, 32, 44), -1)
    cv2.addWeighted(overlay, 0.62, canvas, 0.38, 0, canvas)
    cv2.rectangle(canvas, (x0, y0), (x0 + panel_w, y0 + panel_h), (0, 212, 187), 1)

    font = load_font(font_size)
    if font is None:
        for index, text in enumerate(lines):
            cv2.putText(
                canvas, text, (x0 + 12, y0 + line_height * (index + 1)),
                cv2.FONT_HERSHEY_SIMPLEX, font_size / 30.0, (255, 255, 255), 1, cv2.LINE_AA,
            )
        return canvas

    pil_image = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)
    for index, text in enumerate(lines):
        draw.text((x0 + 12, y0 + 8 + line_height * index), text, fill=(240, 245, 250), font=font)
    return cv2.cvtColor(np.asarray(pil_image), cv2.COLOR_RGB2BGR)
