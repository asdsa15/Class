# -*- coding: utf-8 -*-
"""MySQL 数据库改造验证脚本（对应改造报告第 32、33、35、36、39、40 节）。

验证内容：

1. `.env` 中的连接串是否生效、是否真正连接 MySQL（dialect = mysql）；
2. `class_detection` 库与 5 张业务表是否存在，表结构是否与 ORM 模型一致；
3. 完整业务链路是否能把数据写进 MySQL：
   登录 -> 课程(course) -> 课堂(class_session) -> YOLOv8 检测
   -> detection_record -> 专注度算法 -> attention_record -> 课堂报告；
4. 验证完成后自动清理本次产生的测试数据（课程级联删除）。

运行方式（项目根目录）::

    .venv\\Scripts\\python.exe tests\\check_mysql.py

如需保留验证数据（用于答辩演示的历史记录），追加参数::

    .venv\\Scripts\\python.exe tests\\check_mysql.py --keep
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 验证过程产生的标注图写入临时目录，避免污染项目 results / uploads
_TEMP_DIR = Path(tempfile.mkdtemp(prefix="classroom_mysqlcheck_"))
os.environ.setdefault("CLASSROOM_RESULT_DIR", str(_TEMP_DIR / "results"))
os.environ.setdefault("CLASSROOM_UPLOAD_DIR", str(_TEMP_DIR / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

import config  # noqa: E402
from database.database import database_info, engine  # noqa: E402
from main import app  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []
KEEP_DATA = "--keep" in sys.argv

TABLES = ["user", "course", "class_session", "detection_record", "attention_record"]


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    mark = "通过" if condition else "失败"
    print(f"  [{mark}] {name}" + (f" —— {detail}" if detail else ""))


def row_count(table: str) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)


def check_connection() -> None:
    print("\n=== 一、数据库连接 ===")
    info = database_info()
    print(f"  连接串：{info['url']}")
    check("已连接 MySQL（dialect = mysql）", info["dialect"] == "mysql", str(info["dialect"]))
    check("未回退 SQLite（fallback_to_sqlite = false）",
          info["fallback_to_sqlite"] is False, str(info["fallback_to_sqlite"]))
    with engine.connect() as connection:
        version, current_db = connection.execute(text("SELECT VERSION(), DATABASE()")).fetchone()
    check("数据库版本为 MySQL 8.x", str(version).startswith("8."), str(version))
    check("当前数据库为 class_detection", current_db == "class_detection", str(current_db))


def check_schema() -> None:
    print("\n=== 二、表结构 ===")
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    check("5 张业务表齐全", all(table in existing for table in TABLES), ", ".join(sorted(existing)))

    from database.models import (  # 延迟导入，避免影响启动日志顺序
        AttentionRecord,
        ClassSession,
        Course,
        DetectionRecord,
        User,
    )

    for model in (User, Course, ClassSession, DetectionRecord, AttentionRecord):
        table = model.__tablename__
        if table not in existing:
            check(f"{table} 表存在", False)
            continue
        db_columns = {column["name"] for column in inspector.get_columns(table)}
        orm_columns = {column.name for column in model.__table__.columns}
        missing = orm_columns - db_columns
        check(f"{table} 字段与 ORM 模型一致", not missing,
              f"缺少字段：{', '.join(sorted(missing))}" if missing else f"{len(orm_columns)} 个字段")

    foreign_keys = {
        "course": "user",
        "class_session": "course",
        "detection_record": "class_session",
        "attention_record": "class_session",
    }
    for table, referent in foreign_keys.items():
        targets = {fk["referred_table"] for fk in inspector.get_foreign_keys(table)}
        check(f"{table} 外键指向 {referent}", referent in targets, ", ".join(sorted(targets)))

    for table in TABLES:
        print(f"  · {table} 现有 {row_count(table)} 条记录")


def check_business_chain() -> None:
    print("\n=== 三、业务链路写入 MySQL ===")
    before = {table: row_count(table) for table in TABLES}
    course = None
    session = None

    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        check("登录成功（user 表）", response.status_code == 200, f"HTTP {response.status_code}")
        if response.status_code != 200:
            return
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        with engine.connect() as connection:
            admin_count = int(
                connection.execute(
                    text("SELECT COUNT(*) FROM user WHERE username = 'admin'")
                ).scalar()
                or 0
            )
        check("管理员账号存在于 user 表", admin_count == 1,
              f"user 表共 {row_count('user')} 条记录，admin {admin_count} 条")

        response = client.post(
            "/api/courses",
            json={
                "course_name": "MySQL 接入验证课程",
                "class_name": "验证班级",
                "classroom": "验证教室",
                "description": "由 tests/check_mysql.py 自动创建",
            },
            headers=headers,
        )
        check("创建课程写入 course 表", response.status_code == 201, f"HTTP {response.status_code}")
        course = response.json()

        response = client.post("/api/classrooms/start", json={"course_id": course["id"]}, headers=headers)
        check("开始课堂写入 class_session 表", response.status_code == 201, f"HTTP {response.status_code}")
        session = response.json()

        image_path = PROJECT_ROOT / "test-file" / "images" / "0001059.jpg"
        if image_path.exists():
            with open(image_path, "rb") as fp:
                response = client.post(
                    "/api/detection/image",
                    files={"file": (image_path.name, fp, "image/jpeg")},
                    data={"session_id": str(session["id"]), "save": "true", "return_base64": "false"},
                    headers=headers,
                )
            payload = response.json() if response.status_code == 200 else {}
            check("图片检测成功", response.status_code == 200, f"HTTP {response.status_code}")
            check("检测结果写入 detection_record 表",
                  row_count("detection_record") > before["detection_record"],
                  f"{before['detection_record']} -> {row_count('detection_record')} 条")
            check("专注度写入 attention_record 表",
                  row_count("attention_record") > before["attention_record"],
                  f"{before['attention_record']} -> {row_count('attention_record')} 条")
            print(f"  · 本次检测：{len(payload.get('detections', []))} 个目标，"
                  f"专注度 {payload.get('attention', {}).get('score')}%")

        response = client.post(f"/api/classrooms/{session['id']}/stop", headers=headers)
        check("结束课堂（class_session 状态更新）",
              response.status_code == 200 and response.json()["status"] == "finished")

        report = client.get(f"/api/reports/{session['id']}", headers=headers).json()
        check("课堂报告可从 MySQL 生成",
              report.get("session_id") == session["id"] and len(report.get("behaviors", [])) == 6,
              f"平均专注度 {report.get('avg_attention')}%，采样 {report.get('record_count')} 次")

        if not KEEP_DATA and course is not None:
            response = client.delete(f"/api/courses/{course['id']}", headers=headers)
            check("清理测试数据（课程级联删除）", response.status_code == 200,
                  "、".join(f"{table} {row_count(table)} 条" for table in TABLES))


def main() -> int:
    print("class_Detection_end —— MySQL 改造验证")
    print(f"项目根目录：{PROJECT_ROOT}")
    print(f"数据库名称：{config.DB_NAME}")
    if KEEP_DATA:
        print("（--keep：保留本次验证产生的数据）")

    check_connection()
    check_schema()
    check_business_chain()

    print("\n=== 验证结果 ===")
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        for item in FAILED:
            print(f"  - {item}")
        return 1
    print("\n结论：系统已连接 MySQL（class_detection），业务数据链路完整 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
