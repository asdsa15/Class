# -*- coding: utf-8 -*-
"""系统测试用例脚本（对应《项目优化与功能补充报告》第 16 节）。

按报告给出的用户模块测试（U01~U09）与业务测试（C01~C08）逐条执行，
并额外补充账号禁用、登录失败限制两项安全用例，
最后生成 Markdown 测试用例表：``docs/测试用例表.md``（可直接作为论文"系统测试"章节内容）。

运行方式（项目根目录）::

    .venv\\Scripts\\python.exe tests\\test_cases.py

说明：脚本使用临时 SQLite 数据库与临时文件目录，不会影响正式 MySQL 数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_TEMP_DIR = Path(tempfile.mkdtemp(prefix="classroom_testcases_"))
os.environ.setdefault("CLASSROOM_DB_URL", f"sqlite:///{_TEMP_DIR / 'cases.db'}")
os.environ.setdefault("CLASSROOM_SQLITE_FALLBACK", "0")
os.environ.setdefault("CLASSROOM_SECRET_KEY", "test-cases-secret")
os.environ.setdefault("CLASSROOM_DEVICE", "cpu")
os.environ.setdefault("CLASSROOM_RESULT_DIR", str(_TEMP_DIR / "results"))
os.environ.setdefault("CLASSROOM_UPLOAD_DIR", str(_TEMP_DIR / "uploads"))
# 视频用例降低采样密度，缩短测试时间
os.environ.setdefault("CLASSROOM_VIDEO_INTERVAL", "120")

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
from detection.image_utils import bgr_to_base64, imread  # noqa: E402
from main import app  # noqa: E402

# (编号, 测试内容, 预期结果)
CASES = [
    ("U01", "使用正确账号密码登录", "登录成功并返回令牌"),
    ("U02", "使用错误密码登录", "登录失败（401）"),
    ("U03", "使用不存在的账号登录", "登录失败（401）"),
    ("U04", "勾选「记住密码」登录", "登录成功，Cookie 为持久 Cookie（带有效期）"),
    ("U05", "不勾选「记住密码」登录", "登录成功，Cookie 为会话 Cookie（不写有效期）"),
    ("U06", "教师访问用户管理接口与页面", "接口返回 403，页面跳回首页"),
    ("U07", "管理员创建教师账号", "创建成功（201）"),
    ("U08", "创建重复用户名", "提示账号已存在（400）"),
    ("U09", "删除当前登录的管理员账号", "被拒绝（400）"),
    ("U10", "登录失败次数超过限制", "账号临时锁定（429）"),
    ("U11", "禁用账号后使用该账号登录", "登录被拒绝（403）"),
    ("C01", "新建课程", "创建成功（201）"),
    ("C02", "开始一次课堂", "课堂状态为进行中"),
    ("C03", "上传图片进行行为检测", "返回检测框、行为统计与专注度"),
    ("C04", "提交视频检测任务", "后台任务执行完成并生成结果视频"),
    ("C05", "WebSocket 实时检测", "连接成功并返回检测结果帧"),
    ("C06", "结束课堂", "课堂状态为已结束并记录时长"),
    ("C07", "查询历史课堂列表", "能查询到本次课堂记录"),
    ("C08", "查看课堂报告", "生成平均 / 最高 / 最低专注度与行为统计"),
]

RECORDS: list[dict] = []


def record(
    case_id: str, name: str, expected: str, passed: bool, actual: str, skipped: bool = False
) -> None:
    result = "跳过" if skipped else ("通过" if passed else "失败")
    RECORDS.append(
        {
            "id": case_id,
            "name": name,
            "expected": expected,
            "actual": actual,
            "result": result,
        }
    )
    print(f"  [{RECORDS[-1]['result']}] {case_id} {name} —— {actual}")


def case(case_id: str) -> tuple[str, str]:
    for item in CASES:
        if item[0] == case_id:
            return item[1], item[2]
    return case_id, ""


def run() -> int:
    teacher_headers: dict = {}
    admin_headers: dict = {}
    session_id = None
    course_id = None
    video_task_id = None
    detection_data = False

    with TestClient(app) as client:
        print("=== 用户模块测试 ===")
        # U01
        name, expected = case("U01")
        response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        passed = response.status_code == 200 and bool(response.json().get("access_token"))
        admin_headers = {"Authorization": f"Bearer {response.json().get('access_token', '')}"}
        record("U01", name, expected, passed, f"HTTP {response.status_code}")

        # U02
        name, expected = case("U02")
        response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})
        record("U02", name, expected, response.status_code == 401, f"HTTP {response.status_code}")

        # U03
        name, expected = case("U03")
        response = client.post("/api/auth/login", json={"username": "no-such-user", "password": "whatever123"})
        record("U03", name, expected, response.status_code == 401, f"HTTP {response.status_code}")

        # U04 / U05：检查 Set-Cookie 是否带 Max-Age
        name, expected = case("U04")
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123", "remember_me": True},
        )
        cookie = response.headers.get("set-cookie", "")
        passed = response.status_code == 200 and "Max-Age=" in cookie and response.json().get("remember_me") is True
        record("U04", name, expected, passed, "Cookie 含 Max-Age（30 天）" if passed else f"cookie={cookie[:60]}")

        name, expected = case("U05")
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123", "remember_me": False},
        )
        cookie = response.headers.get("set-cookie", "")
        passed = response.status_code == 200 and "Max-Age=" not in cookie
        record("U05", name, expected, passed, "会话 Cookie（无 Max-Age）" if passed else f"cookie={cookie[:60]}")

        # U07 先创建教师，便于 U06 测试
        name, expected = case("U07")
        response = client.post(
            "/api/auth/users",
            json={
                "username": "teacher01",
                "real_name": "张老师",
                "password": "Teacher@2026",
                "role": "teacher",
            },
            headers=admin_headers,
        )
        record("U07", name, expected, response.status_code == 201, f"HTTP {response.status_code}")

        login = client.post(
            "/api/auth/login", json={"username": "teacher01", "password": "Teacher@2026"}
        )
        teacher_headers = {"Authorization": f"Bearer {login.json().get('access_token', '')}"}

        # U06
        name, expected = case("U06")
        api_response = client.get("/api/auth/users", headers=teacher_headers)
        page_response = client.get("/users", headers=teacher_headers, follow_redirects=False)
        passed = api_response.status_code == 403 and page_response.status_code == 302
        record(
            "U06",
            name,
            expected,
            passed,
            f"接口 HTTP {api_response.status_code}，页面 HTTP {page_response.status_code}",
        )

        # U08
        name, expected = case("U08")
        response = client.post(
            "/api/auth/users",
            json={"username": "teacher01", "password": "Teacher@2026", "role": "teacher"},
            headers=admin_headers,
        )
        record("U08", name, expected, response.status_code == 400, f"HTTP {response.status_code}")

        # U09
        name, expected = case("U09")
        me = client.get("/api/auth/me", headers=admin_headers).json()
        response = client.delete(f"/api/auth/users/{me['id']}", headers=admin_headers)
        record("U09", name, expected, response.status_code == 400, f"HTTP {response.status_code}")

        # U10 登录失败次数限制（默认 5 次）
        name, expected = case("U10")
        status = 0
        for _ in range(config.LOGIN_MAX_ATTEMPTS + 1):
            status = client.post(
                "/api/auth/login", json={"username": "teacher01", "password": "bad-password"}
            ).status_code
        record("U10", name, expected, status == 429, f"连续失败后 HTTP {status}")
        # 解除锁定，避免影响后续用例
        from routers import auth as auth_module

        auth_module._FAILED_ATTEMPTS.clear()

        # U11 禁用账号
        name, expected = case("U11")
        users = client.get("/api/auth/users", headers=admin_headers).json()
        teacher = [item for item in users if item["username"] == "teacher01"][0]
        client.put(
            f"/api/auth/users/{teacher['id']}", json={"status": 0}, headers=admin_headers
        )
        response = client.post(
            "/api/auth/login", json={"username": "teacher01", "password": "Teacher@2026"}
        )
        record("U11", name, expected, response.status_code == 403, f"HTTP {response.status_code}")
        client.put(
            f"/api/auth/users/{teacher['id']}", json={"status": 1}, headers=admin_headers
        )

        print("\n=== 业务测试 ===")
        # C01
        name, expected = case("C01")
        response = client.post(
            "/api/courses",
            json={"course_name": "测试课程", "class_name": "测试班级", "classroom": "A101"},
            headers=admin_headers,
        )
        course_id = response.json().get("id") if response.status_code == 201 else None
        record("C01", name, expected, response.status_code == 201, f"HTTP {response.status_code}")

        # C02
        name, expected = case("C02")
        response = client.post(
            "/api/classrooms/start", json={"course_id": course_id}, headers=admin_headers
        )
        session_id = response.json().get("id") if response.status_code == 201 else None
        passed = response.status_code == 201 and response.json().get("status") == "running"
        record("C02", name, expected, passed, f"课堂ID={session_id}，状态={response.json().get('status')}")

        # C03
        name, expected = case("C03")
        image_path = PROJECT_ROOT / "test-file" / "images" / "0001059.jpg"
        if not image_path.exists():
            record("C03", name, expected, False, "缺少测试图片 test-file/images/0001059.jpg", skipped=True)
            image_available = False
        else:
            image_available = True
            with open(image_path, "rb") as fp:
                response = client.post(
                    "/api/detection/image",
                    files={"file": (image_path.name, fp, "image/jpeg")},
                    data={"session_id": str(session_id), "save": "true", "return_base64": "false"},
                    headers=admin_headers,
                )
            payload = response.json() if response.status_code == 200 else {}
            passed = (
                response.status_code == 200
                and isinstance(payload.get("detections"), list)
                and len(payload.get("behaviors", [])) == 6
                and payload.get("attention", {}).get("score") is not None
            )
            record(
                "C03",
                name,
                expected,
                passed,
                f"目标 {len(payload.get('detections', []))} 个，专注度 {payload.get('attention', {}).get('score')}%",
            )
            detection_data = detection_data or passed

        # C04 视频检测（后台任务；TestClient 会等待后台任务结束）
        name, expected = case("C04")
        video_path = PROJECT_ROOT / "test-file" / "vedios" / "aspose_video.mp4"
        if not video_path.exists():
            record("C04", name, expected, False, "缺少测试视频 test-file/vedios/aspose_video.mp4", skipped=True)
        else:
            with open(video_path, "rb") as fp:
                response = client.post(
                    "/api/detection/video",
                    files={"file": (video_path.name, fp, "video/mp4")},
                    data={"session_id": str(session_id)},
                    headers=admin_headers,
                )
            video_task_id = response.json().get("task_id")
            task = client.get(f"/api/detection/video/{video_task_id}", headers=admin_headers).json()
            passed = task.get("status") == "finished" and bool(task.get("result_video_url"))
            record(
                "C04",
                name,
                expected,
                passed,
                f"处理 {task.get('processed_frames')} 帧，平均专注度 {task.get('avg_attention')}%",
            )
            detection_data = detection_data or passed

        # C05 WebSocket 实时检测
        name, expected = case("C05")
        ws_image_path = PROJECT_ROOT / "test-file" / "images" / "0002017.jpg"
        image = imread(ws_image_path) if ws_image_path.exists() else None
        if image is None:
            record("C05", name, expected, False, "缺少测试图片 test-file/images/0002017.jpg", skipped=True)
        else:
            token = admin_headers["Authorization"].split(" ")[1]
            with client.websocket_connect(f"/ws/classroom/{session_id}?token={token}") as websocket:
                websocket.receive_json()  # ready
                websocket.send_json({"type": "frame", "image": bgr_to_base64(image, quality=70)})
                message = websocket.receive_json()
            passed = message.get("type") == "result" and message.get("attention", {}).get("score") is not None
            record("C05", name, expected, passed, f"返回类型={message.get('type')}")

        # C06
        name, expected = case("C06")
        response = client.post(f"/api/classrooms/{session_id}/stop", headers=admin_headers)
        passed = response.status_code == 200 and response.json().get("status") == "finished"
        record("C06", name, expected, passed, f"状态={response.json().get('status')}")

        # C07
        name, expected = case("C07")
        rows = client.get("/api/classrooms", headers=admin_headers).json()
        passed = any(item["id"] == session_id for item in rows)
        record("C07", name, expected, passed, f"历史课堂 {len(rows)} 条")

        # C08
        name, expected = case("C08")
        report = client.get(f"/api/reports/{session_id}", headers=admin_headers).json()
        if detection_data:
            passed = (
                report.get("avg_attention") is not None
                and len(report.get("behaviors", [])) == 6
                and len(report.get("summary", [])) > 0
            )
            actual = (
                f"平均 {report.get('avg_attention')}%，最高 {report.get('max_attention')}%，"
                f"最低 {report.get('min_attention')}%"
            )
        else:
            # 无测试素材时不产生检测数据，验证报告接口仍能正常返回结构
            passed = len(report.get("behaviors", [])) == 6 and len(report.get("summary", [])) > 0
            actual = "无检测数据时报告结构正常（平均专注度为 --）"
        record("C08", name, expected, passed, actual)

    write_markdown()
    failed = [item for item in RECORDS if item["result"] == "失败"]
    skipped = [item for item in RECORDS if item["result"] == "跳过"]
    print(
        f"\n测试用例执行完成：通过 {len(RECORDS) - len(failed) - len(skipped)} 项，"
        f"失败 {len(failed)} 项，跳过 {len(skipped)} 项"
    )
    print("测试用例表已写入：docs/测试用例表.md")
    return 1 if failed else 0


def write_markdown() -> None:
    lines = [
        "# 系统测试用例表",
        "",
        "> 由 `tests/test_cases.py` 自动生成，对应《项目优化与功能补充报告》第 16 节。",
        "> 执行时间：" + __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "| 编号 | 测试内容 | 预期结果 | 实际结果 | 测试结论 |",
        "|---|---|---|---|---|",
    ]
    for item in RECORDS:
        lines.append(
            f"| {item['id']} | {item['name']} | {item['expected']} | {item['actual']} | {item['result']} |"
        )
    passed = len([item for item in RECORDS if item["result"] == "通过"])
    skipped = len([item for item in RECORDS if item["result"] == "跳过"])
    lines += [
        "",
        f"合计 {len(RECORDS)} 条用例，通过 {passed} 条，失败 {len(RECORDS) - passed - skipped} 条，跳过 {skipped} 条。",
        "",
        "> 说明：U04/U05 的「记住密码」实现为记住登录状态——浏览器仅保存账号，",
        "> 不保存明文密码；勾选后登录 Cookie 有效期延长至 30 天，未勾选时为会话 Cookie。",
        "",
    ]
    target = PROJECT_ROOT / "docs" / "测试用例表.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(run())
