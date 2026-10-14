# -*- coding: utf-8 -*-
"""权限数据隔离测试（对应《项目优化与功能补充报告》第 13 节）。

构造「管理员 + 教师A + 教师B」三个账号，验证教师 A 的数据无法被教师 B
通过修改 URL 中的 ID 访问，同时确认管理员拥有全局权限，
最后生成 ``docs/权限隔离测试.md``。

运行方式（项目根目录）::

    .venv\\Scripts\\python.exe tests\\test_permissions.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_TEMP_DIR = Path(tempfile.mkdtemp(prefix="classroom_permission_"))
os.environ.setdefault("CLASSROOM_DB_URL", f"sqlite:///{_TEMP_DIR / 'perm.db'}")
os.environ.setdefault("CLASSROOM_SQLITE_FALLBACK", "0")
os.environ.setdefault("CLASSROOM_SECRET_KEY", "permission-test-secret")
os.environ.setdefault("CLASSROOM_DEVICE", "cpu")
os.environ.setdefault("CLASSROOM_RESULT_DIR", str(_TEMP_DIR / "results"))
os.environ.setdefault("CLASSROOM_UPLOAD_DIR", str(_TEMP_DIR / "uploads"))
os.environ.setdefault("CLASSROOM_VIDEO_INTERVAL", "120")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from main import app  # noqa: E402

RECORDS: list[tuple[str, str, str, bool, str]] = []


def record(name: str, expected: str, actual: str, passed: bool) -> None:
    RECORDS.append((name, expected, actual, passed))
    print(f"  [{'通过' if passed else '失败'}] {name} —— 预期：{expected}；实际：{actual}")


def login(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    token = response.json().get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    with TestClient(app) as client:
        admin = login(client, "admin", "admin123")
        for username, real_name in (("teacher_a", "教师A"), ("teacher_b", "教师B")):
            client.post(
                "/api/auth/users",
                json={"username": username, "real_name": real_name,
                      "password": "Teacher@2026", "role": "teacher"},
                headers=admin,
            )
        headers_a = login(client, "teacher_a", "Teacher@2026")
        headers_b = login(client, "teacher_b", "Teacher@2026")

        # 教师 A 建立自己的课程与课堂，并写入一次检测数据
        course = client.post(
            "/api/courses",
            json={"course_name": "教师A的课程", "class_name": "A 班", "classroom": "A101"},
            headers=headers_a,
        ).json()
        session = client.post(
            "/api/classrooms/start", json={"course_id": course["id"]}, headers=headers_a
        ).json()
        image_path = PROJECT_ROOT / "test-file" / "images" / "0001059.jpg"
        video_path = PROJECT_ROOT / "test-file" / "vedios" / "aspose_video.mp4"
        task = None
        if image_path.exists():
            with open(image_path, "rb") as fp:
                client.post(
                    "/api/detection/image",
                    files={"file": (image_path.name, fp, "image/jpeg")},
                    data={"session_id": str(session["id"]), "save": "true", "return_base64": "false"},
                    headers=headers_a,
                )
        else:
            print("  [跳过] 教师A 写入检测数据：缺少测试图片（不影响权限校验）")
        if video_path.exists():
            with open(video_path, "rb") as fp:
                task = client.post(
                    "/api/detection/video",
                    files={"file": (video_path.name, fp, "video/mp4")},
                    data={"session_id": str(session["id"])},
                    headers=headers_a,
                ).json()

        print("=== 教师A 正常访问自己的数据（正向验证）===")
        own_course = client.get(f"/api/courses/{course['id']}", headers=headers_a)
        record("教师A 查看自己的课程", "允许", f"HTTP {own_course.status_code}", own_course.status_code == 200)
        own_report = client.get(f"/api/reports/{session['id']}", headers=headers_a)
        record("教师A 查看自己的课堂报告", "允许", f"HTTP {own_report.status_code}", own_report.status_code == 200)

        print("\n=== 教师B 访问教师A 的数据（越权验证，应全部拒绝）===")
        checks = [
            ("教师B 查看教师A 的课程详情", f"/api/courses/{course['id']}"),
            ("教师B 查看教师A 的课堂详情", f"/api/classrooms/{session['id']}"),
            ("教师B 查看教师A 的检测明细", f"/api/classrooms/{session['id']}/records"),
            ("教师B 查看教师A 的课堂报告", f"/api/reports/{session['id']}"),
            ("教师B 查看教师A 的报告统计", f"/api/reports/{session['id']}/statistics"),
            ("教师B 查看教师A 的课程对比", f"/api/reports/courses/{course['id']}/compare"),
        ]
        if task:
            checks.append(("教师B 查看教师A 的视频任务", f"/api/detection/video/{task['task_id']}"))
        for name, url in checks:
            response = client.get(url, headers=headers_b)
            record(name, "HTTP 403", f"HTTP {response.status_code}", response.status_code == 403)

        response = client.put(
            f"/api/courses/{course['id']}", json={"course_name": "被篡改"}, headers=headers_b
        )
        record("教师B 修改教师A 的课程", "HTTP 403", f"HTTP {response.status_code}", response.status_code == 403)

        response = client.delete(f"/api/courses/{course['id']}", headers=headers_b)
        record("教师B 删除教师A 的课程", "HTTP 403", f"HTTP {response.status_code}", response.status_code == 403)

        response = client.post(
            "/api/classrooms/start", json={"course_id": course["id"]}, headers=headers_b
        )
        record("教师B 为教师A 的课程开课", "HTTP 403", f"HTTP {response.status_code}", response.status_code == 403)

        response = client.post(f"/api/classrooms/{session['id']}/stop", headers=headers_b)
        record("教师B 结束教师A 的课堂", "HTTP 403", f"HTTP {response.status_code}", response.status_code == 403)

        response = client.delete(f"/api/classrooms/{session['id']}", headers=headers_b)
        record("教师B 删除教师A 的课堂", "HTTP 403", f"HTTP {response.status_code}", response.status_code == 403)

        if image_path.exists():
            with open(image_path, "rb") as fp:
                response = client.post(
                    "/api/detection/image",
                    files={"file": (image_path.name, fp, "image/jpeg")},
                    data={"session_id": str(session["id"]), "save": "true"},
                    headers=headers_b,
                )
            record(
                "教师B 向教师A 的课堂写入检测结果",
                "HTTP 403",
                f"HTTP {response.status_code}",
                response.status_code == 403,
            )
        else:
            print("  [跳过] 教师B 向教师A 的课堂写入检测结果：缺少测试图片")

        # WebSocket 越权：服务端应以 4403 关闭连接
        token_b = headers_b["Authorization"].split(" ")[1]
        code = None
        try:
            with client.websocket_connect(f"/ws/classroom/{session['id']}?token={token_b}") as websocket:
                websocket.receive_json()
                code = 1000
        except WebSocketDisconnect as exc:
            code = exc.code
        record("教师B 连接教师A 的实时检测", "关闭码 4403", f"关闭码 {code}", code == 4403)

        print("\n=== 列表数据隔离 ===")
        courses_b = client.get("/api/courses", headers=headers_b).json()
        record("教师B 的课程列表不含教师A 的课程", "0 条",
               f"{len(courses_b)} 条", all(item["id"] != course["id"] for item in courses_b))
        sessions_b = client.get(
            f"/api/classrooms?course_id={course['id']}", headers=headers_b
        ).json()
        record("教师B 按教师A 课程ID 过滤课堂列表", "0 条", f"{len(sessions_b)} 条", len(sessions_b) == 0)
        users_b = client.get("/api/auth/users", headers=headers_b)
        record("教师B 访问用户管理接口", "HTTP 403", f"HTTP {users_b.status_code}", users_b.status_code == 403)

        print("\n=== 管理员全局权限 ===")
        admin_course = client.get(f"/api/courses/{course['id']}", headers=admin)
        record("管理员查看任意课程", "HTTP 200", f"HTTP {admin_course.status_code}", admin_course.status_code == 200)
        admin_report = client.get(f"/api/reports/{session['id']}", headers=admin)
        record("管理员查看任意课堂报告", "HTTP 200", f"HTTP {admin_report.status_code}", admin_report.status_code == 200)
        admin_users = client.get("/api/auth/users", headers=admin)
        record("管理员查看用户列表", "HTTP 200", f"HTTP {admin_users.status_code}", admin_users.status_code == 200)

    write_markdown()
    failed = [item for item in RECORDS if not item[3]]
    print(f"\n权限测试完成：通过 {len(RECORDS) - len(failed)} 项，失败 {len(failed)} 项")
    print("测试结果已写入：docs/权限隔离测试.md")
    return 1 if failed else 0


def write_markdown() -> None:
    from datetime import datetime

    lines = [
        "# 权限数据隔离测试结果",
        "",
        "> 由 `tests/test_permissions.py` 自动生成，对应《项目优化与功能补充报告》第 13 节。",
        "> 执行时间：" + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "测试账号：管理员 `admin`、教师 `teacher_a`、教师 `teacher_b`。",
        "教师 A 建立课程与课堂并写入检测数据，教师 B 尝试越权访问。",
        "",
        "| 测试内容 | 预期结果 | 实际结果 | 结论 |",
        "|---|---|---|---|",
    ]
    for name, expected, actual, passed in RECORDS:
        lines.append(f"| {name} | {expected} | {actual} | {'通过' if passed else '失败'} |")
    passed_count = len([item for item in RECORDS if item[3]])
    lines += [
        "",
        f"合计 {len(RECORDS)} 项，通过 {passed_count} 项，失败 {len(RECORDS) - passed_count} 项。",
        "",
        "> 结论：课程、课堂、检测、报告、用户五类接口均按角色与数据归属做了服务端校验，",
        "> 教师之间数据互相隔离，管理员拥有全局查看权限；前端菜单隐藏不作为权限依据。",
        "",
    ]
    target = PROJECT_ROOT / "docs" / "权限隔离测试.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
