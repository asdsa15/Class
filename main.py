# -*- coding: utf-8 -*-
"""基于 Python Web 的课堂专注度分析系统 —— FastAPI 应用入口。

启动方式::

    python main.py
    # 或
    uvicorn main:app --host 127.0.0.1 --port 8000

系统结构（对应修改报告第 15、26、33 节）::

    main.py            应用入口 / 路由注册 / 日志
    config.py          全局配置
    database/          MySQL / SQLite 数据模型与会话
    schemas/           Pydantic 数据校验模型
    detection/         YOLOv8 检测 + 行为统计 + 专注度计算
    services/          检测流程、视频任务、报告统计、安全工具
    routers/           认证 / 课程 / 课堂 / 检测 / 报告 / 页面
    templates/ static/ Web 前端
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import config

try:
    from database.database import database_info, init_db
    from detection.detector import detector_status, get_detector
    from routers import auth, classroom, course, detection, pages, report
except RuntimeError as exc:  # 数据库未配置或连接失败时给出可操作的启动提示
    print("\n" + "=" * 66)
    print("[启动失败] " + str(exc))
    print("=" * 66 + "\n")
    raise SystemExit(1)

APP_NAME = "基于 Python Web 的课堂专注度分析系统"
APP_VERSION = "1.0.0"

logger = logging.getLogger("classroom")


def setup_logging() -> None:
    """同时输出到控制台与 logs/app.log，便于排查问题与论文附录截图。"""
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        file_handler = logging.FileHandler(config.LOG_DIR / "app.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception:  # pragma: no cover - 日志文件不可写时忽略
        pass


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动：创建数据表、写入默认管理员，并在后台预热 YOLOv8 模型。"""
    init_db()
    info = database_info()
    logger.info("数据库：%s", info["url"])
    if info["fallback_to_sqlite"]:
        logger.warning(
            "当前使用 SQLite 回退模式（MySQL 未连接）。如需使用 MySQL，"
            "请启动 MySQL 并在 .env 中配置 CLASSROOM_DB_URL。"
        )
    threading.Thread(target=get_detector().warmup, daemon=True).start()
    logger.info("%s v%s 启动完成", APP_NAME, APP_VERSION)
    yield
    logger.info("服务已停止")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "以原 YOLOv8 课堂行为检测成果为基础，重构为 FastAPI + Web 前端的"
        "课堂专注度分析系统：图片 / 视频 / 实时摄像头检测、行为统计、"
        "专注度计算、课堂管理与统计报告。"
    ),
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
app.mount("/results", StaticFiles(directory=str(config.RESULT_DIR)), name="results")

# 页面路由（不需要前缀），API 路由统一使用 /api 前缀
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(course.router)
app.include_router(classroom.router)
app.include_router(detection.router)
app.include_router(report.router)


@app.get("/api/system/status", tags=["系统"], summary="系统与模型运行状态")
def system_status() -> dict:
    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "model": detector_status(),
        "database": database_info(),
        "config": config.config_snapshot(),
    }


@app.get("/health", tags=["系统"], summary="健康检查")
def health() -> dict:
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}


if __name__ == "__main__":
    print(f"\n{APP_NAME} v{APP_VERSION}")
    print(f"访问地址： http://{config.SERVER_HOST}:{config.SERVER_PORT}")
    print("默认账号： admin / admin123\n")
    uvicorn.run(
        "main:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=False,
        log_level="info",
    )
