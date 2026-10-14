# -*- coding: utf-8 -*-
"""数据库连接与会话管理。

设计说明（对应修改报告第 16、17 节）：

* 默认使用 **MySQL**（mysql+pymysql://...），数据表由 SQLAlchemy 自动创建；
* 若 MySQL 未启动或账号不可用，在 CLASSROOM_SQLITE_FALLBACK=1（默认）时
  自动回退到项目根目录下的 SQLite 文件，保证系统在任何机器上都能直接运行，
  便于答辩演示与自动化测试；
* 所有业务代码统一通过 get_db() 依赖注入数据库会话。
"""

from __future__ import annotations

import logging
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

import config

logger = logging.getLogger("classroom.database")


class DatabaseConfigError(RuntimeError):
    """数据库未配置或连接失败（且不允许回退 SQLite）时抛出。"""


CONFIG_HINT = (
    "请在项目根目录创建 .env 文件（可复制 .env.example），写入：\n"
    "    CLASSROOM_DB_URL=mysql+pymysql://root:<你的MySQL密码>@127.0.0.1:3306/class_detection?charset=utf8mb4\n"
    "    CLASSROOM_SQLITE_FALLBACK=0\n"
    "并确认 MySQL 服务已启动、class_detection 数据库已创建（可执行 class_detection.sql）。"
)


class Base(DeclarativeBase):
    """所有业务数据模型的基类。"""


def _mask(url: str) -> str:
    """隐藏数据库连接串中的密码，便于日志安全输出。"""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:  # pragma: no cover
        return url


def _create_engine(url: str) -> Engine:
    kwargs: dict = {"echo": config.DB_ECHO, "pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["connect_args"] = {"connect_timeout": config.DB_CONNECT_TIMEOUT}
        kwargs["pool_recycle"] = 3600
    return create_engine(url, **kwargs)


def _init_engine() -> tuple[Engine, str, bool]:
    """建立数据库连接；MySQL 不可用时按配置回退 SQLite。

    返回 (engine, 实际使用的连接串, 是否发生回退)。
    """
    url = (config.DB_URL or "").strip()
    if not url:
        if config.DB_SQLITE_FALLBACK:
            fallback = f"sqlite:///{config.SQLITE_PATH}"
            logger.warning("未配置 CLASSROOM_DB_URL，已回退到 SQLite：%s", config.SQLITE_PATH)
            return _create_engine(fallback), fallback, True
        raise DatabaseConfigError("未配置数据库连接（CLASSROOM_DB_URL 为空）。\n" + CONFIG_HINT)

    try:
        engine = _create_engine(url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("数据库连接成功：%s", _mask(url))
        return engine, url, False
    except Exception as exc:  # MySQL 未启动 / 数据库不存在 / 驱动缺失
        if not config.DB_SQLITE_FALLBACK:
            raise DatabaseConfigError(
                f"MySQL 连接失败：{exc}\n" + CONFIG_HINT
            ) from exc
        fallback = f"sqlite:///{config.SQLITE_PATH}"
        logger.warning("MySQL 连接失败（%s），已自动回退到 SQLite：%s", exc, config.SQLITE_PATH)
        return _create_engine(fallback), fallback, True


engine, ACTIVE_DB_URL, USING_SQLITE_FALLBACK = _init_engine()

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：为每个请求提供独立的数据库会话。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """创建全部数据表，并写入默认管理员账号。"""
    from database import models  # noqa: F401  确保模型已注册到 Base.metadata

    Base.metadata.create_all(bind=engine)
    logger.info("数据表初始化完成（共 %d 张表）", len(Base.metadata.tables))
    _create_default_admin()


def _create_default_admin() -> None:
    """首次启动时创建默认管理员账号，便于直接登录系统。"""
    if not config.CREATE_DEFAULT_ADMIN:
        return

    from database.models import User
    from routers.auth import hash_password

    session = SessionLocal()
    try:
        username = config.DEFAULT_ADMIN["username"]
        if session.query(User).filter(User.username == username).first():
            return
        session.add(
            User(
                username=username,
                password=hash_password(config.DEFAULT_ADMIN["password"]),
                real_name=config.DEFAULT_ADMIN["real_name"],
                role=config.DEFAULT_ADMIN["role"],
            )
        )
        session.commit()
        logger.info("已创建默认管理员账号：%s", username)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_info() -> dict:
    """数据库运行信息，供 /api/system/status 展示。"""
    return {
        "url": _mask(ACTIVE_DB_URL),
        "dialect": engine.dialect.name,
        "database_name": config.DB_NAME,
        "is_mysql": engine.dialect.name == "mysql",
        "server_version": server_version(),
        "fallback_to_sqlite": USING_SQLITE_FALLBACK,
        "configured_url": _mask(config.DB_URL),
    }


_SERVER_VERSION: str | None = None


def server_version() -> str:
    """数据库服务版本号（缓存一次，供首页状态展示）。"""
    global _SERVER_VERSION
    if _SERVER_VERSION is None:
        try:
            with engine.connect() as connection:
                _SERVER_VERSION = str(connection.execute(text("SELECT VERSION()")).scalar() or "")
        except Exception:  # pragma: no cover - 查询失败不影响业务
            _SERVER_VERSION = ""
    return _SERVER_VERSION
