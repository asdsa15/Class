# -*- coding: utf-8 -*-
"""数据库结构升级脚本（对已有数据库安全地补充新增字段与索引）。

`class_detection.sql` 用于新建数据库；本脚本用于**已经存在数据的数据库**，
按 information_schema 检查后逐项补建，可重复执行（幂等），不会删除任何数据。

本次升级内容（对应《项目优化与功能补充报告》第 12 节数据库设计优化）：

* user            新增 status（账号状态）、update_time、last_login_time
* class_session   新增 analysis_mode、video_path、result_video_path、created_by
* attention_record 新增 confidence_threshold
* 索引            新增组合索引，提升历史课堂与报告查询效率

运行方式（项目根目录）::

    .venv\\Scripts\\python.exe tools\\migrate_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from database.database import engine  # noqa: E402

# (表名, 字段名, 字段定义)
COLUMNS: list[tuple[str, str, str]] = [
    ("user", "status", "INT NOT NULL DEFAULT 1 COMMENT '账号状态：1 正常 / 0 已禁用'"),
    ("user", "update_time", "DATETIME NULL COMMENT '最近更新时间'"),
    ("user", "last_login_time", "DATETIME NULL COMMENT '最近登录时间'"),
    (
        "class_session",
        "analysis_mode",
        "VARCHAR(20) NOT NULL DEFAULT '' COMMENT '分析方式：image / video / realtime'",
    ),
    ("class_session", "video_path", "VARCHAR(255) NOT NULL DEFAULT '' COMMENT '原始视频路径'"),
    (
        "class_session",
        "result_video_path",
        "VARCHAR(255) NOT NULL DEFAULT '' COMMENT '结果视频路径'",
    ),
    ("class_session", "created_by", "INT NULL COMMENT '创建人用户ID'"),
    (
        "attention_record",
        "confidence_threshold",
        "FLOAT NOT NULL DEFAULT 0 COMMENT '本次检测使用的置信度阈值'",
    ),
]

# (表名, 索引名, 索引列)
INDEXES: list[tuple[str, str, str]] = [
    ("class_session", "ix_session_course_status_time", "course_id, status, start_time"),
    (
        "detection_record",
        "ix_detection_session_behavior_time",
        "session_id, behavior_type, detection_time",
    ),
    ("attention_record", "ix_attention_session_time", "session_id, record_time"),
]


def existing_columns(connection, table: str) -> set[str]:
    rows = connection.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table"
        ),
        {"table": table},
    ).fetchall()
    return {row[0] for row in rows}


def existing_indexes(connection, table: str) -> set[str]:
    rows = connection.execute(
        text(
            "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table"
        ),
        {"table": table},
    ).fetchall()
    return {row[0] for row in rows}


def main() -> int:
    added_columns: list[str] = []
    added_indexes: list[str] = []
    skipped: list[str] = []

    with engine.begin() as connection:
        for table, column, definition in COLUMNS:
            if column in existing_columns(connection, table):
                skipped.append(f"{table}.{column}")
                continue
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
            added_columns.append(f"{table}.{column}")

        for table, index, columns in INDEXES:
            if index in existing_indexes(connection, table):
                skipped.append(index)
                continue
            connection.execute(text(f"ALTER TABLE {table} ADD INDEX {index} ({columns})"))
            added_indexes.append(f"{table}.{index}")

    print("数据库结构升级完成")
    print(f"  新增字段：{len(added_columns)} 个" + (f" -> {', '.join(added_columns)}" if added_columns else ""))
    print(f"  新增索引：{len(added_indexes)} 个" + (f" -> {', '.join(added_indexes)}" if added_indexes else ""))
    print(f"  已存在跳过：{len(skipped)} 项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
