# -*- coding: utf-8 -*-
"""系统自检脚本：一条命令验证改造后的 Web 系统是否正常工作。

覆盖内容：

1. 数据库初始化与默认管理员登录（JWT / Cookie 认证）
2. 课程管理接口（新增、查询）
3. 课堂管理接口（开始课堂、结束课堂）
4. 专注度算法与行为统计算法的单元校验
5. 图片检测接口（真实调用 YOLOv8 模型，模型不可用时自动跳过）
6. 课堂报告、统计、历史列表、仪表盘接口

运行方式（在项目根目录执行）::

    .venv\\Scripts\\python.exe tests\\self_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 自检使用独立的 SQLite 数据库与独立的结果目录，避免污染正式数据
_TEMP_DIR = Path(tempfile.mkdtemp(prefix="classroom_selfcheck_"))
os.environ.setdefault("CLASSROOM_DB_URL", f"sqlite:///{_TEMP_DIR / 'selfcheck.db'}")
os.environ.setdefault("CLASSROOM_SQLITE_FALLBACK", "0")
os.environ.setdefault("CLASSROOM_SECRET_KEY", "self-check-secret")
os.environ.setdefault("CLASSROOM_DEVICE", "cpu")
# 自检时降低视频检测的采样密度，缩短测试时间（仅影响本次自检进程）
os.environ.setdefault("CLASSROOM_VIDEO_INTERVAL", "60")
# 自检产生的检测结果图 / 结果视频写入临时目录，避免污染项目 results、uploads
os.environ.setdefault("CLASSROOM_RESULT_DIR", str(_TEMP_DIR / "results"))
os.environ.setdefault("CLASSROOM_UPLOAD_DIR", str(_TEMP_DIR / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
from detection.attention import calculate_attention  # noqa: E402
from detection.behavior import summarize_detections  # noqa: E402
from detection.detector import Detection  # noqa: E402
from detection.image_utils import bgr_to_base64, imread  # noqa: E402
from main import app  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []
SKIPPED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [通过] {name}" + (f" —— {detail}" if detail else ""))
    else:
        FAILED.append(name)
        print(f"  [失败] {name}" + (f" —— {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def test_algorithms() -> None:
    """专注度算法与行为统计的单元校验。"""
    section("一、算法单元校验")

    # 示例：2 人举手、8 人阅读、15 人写作、3 人使用手机、5 人低头、2 人趴桌
    counts = {
        "hand_raising": 2,
        "reading": 8,
        "writing": 15,
        "using_phone": 3,
        "bowing_head": 5,
        "leaning_over_table": 2,
    }
    result = calculate_attention(counts)
    weighted = 2 * 1.0 + 8 * 1.0 + 15 * 1.0 + 3 * 0.0 + 5 * 0.3 + 2 * 0.2
    expected = round(weighted / 35 * 100, 2)
    check("加权平均公式 A = Σ(Ni×Wi)/Σ(Ni)", abs(result.score - expected) < 0.01,
          f"计算值 {result.score}% ，期望 {expected}%")
    check("学生人数统计", result.student_count == 35, f"student_count={result.student_count}")
    check("专注 / 不专注人数划分", result.focused_count == 25 and result.unfocused_count == 10,
          f"focused={result.focused_count}, unfocused={result.unfocused_count}")
    check("专注度等级判定", result.level in {"非常专注", "比较专注", "中等水平", "偏低", "不专注"},
          f"等级={result.level}")
    empty = calculate_attention({key: 0 for key in counts})
    check("未检测到学生时返回空结果", empty.score is None, f"score={empty.score}")

    detections = [
        Detection(0, "hand-raising", "hand_raising", "举手", 0.91, [0, 0, 10, 10]),
        Detection(0, "hand-raising", "hand_raising", "举手", 0.81, [0, 0, 10, 10]),
        Detection(3, "using phone", "using_phone", "使用手机", 0.70, [0, 0, 10, 10]),
    ]
    summary = summarize_detections(detections)
    check("行为统计数量正确", summary.counts["hand_raising"] == 2 and summary.counts["using_phone"] == 1,
          str(summary.counts))
    check("行为平均置信度计算", abs(summary.confidences["hand_raising"] - 0.86) < 0.001,
          f"avg_conf={summary.confidences['hand_raising']:.3f}")


def test_api_flow(client: TestClient) -> dict:
    """登录 -> 课程 -> 课堂 -> 检测 -> 报告 的完整业务链路。"""
    section("二、接口业务链路")

    # 未登录状态下的访问控制（此时客户端还没有登录 Cookie）
    check("未登录访问受保护接口被拒绝", client.get("/api/courses").status_code == 401)
    check("错误令牌被拒绝",
          client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.value"}).status_code == 401)

    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})
    check("错误密码登录被拒绝", response.status_code == 401)

    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    check("默认管理员登录", response.status_code == 200, f"HTTP {response.status_code}")
    if response.status_code != 200:
        return {}
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    check("携带令牌可访问受保护接口", client.get("/api/courses", headers=headers).status_code == 200)
    check("获取当前用户", client.get("/api/auth/me", headers=headers).json()["username"] == "admin")

    response = client.post(
        "/api/courses",
        json={"course_name": "Python 程序设计", "class_name": "软件工程 1 班", "classroom": "实验楼 A305",
              "description": "自检课程"},
        headers=headers,
    )
    check("新建课程", response.status_code == 201, f"HTTP {response.status_code}")
    course = response.json()
    check("课程列表", any(item["id"] == course["id"] for item in client.get("/api/courses", headers=headers).json()))

    response = client.post("/api/classrooms/start", json={"course_id": course["id"]}, headers=headers)
    check("开始课堂", response.status_code == 201, f"HTTP {response.status_code}")
    session = response.json()
    check("重复开始课堂被拒绝",
          client.post("/api/classrooms/start", json={"course_id": course["id"]}, headers=headers).status_code == 400)

    image_path = PROJECT_ROOT / "test-file" / "images" / "0001059.jpg"
    detection_info = ""
    if not image_path.exists():
        SKIPPED.append("图片检测（缺少测试图片）")
        print(f"  [跳过] 图片检测：测试图片不存在（{image_path}）")
    else:
        with open(image_path, "rb") as fp:
            response = client.post(
                "/api/detection/image",
                files={"file": (image_path.name, fp, "image/jpeg")},
                data={"session_id": str(session["id"]), "save": "true", "return_base64": "false"},
                headers=headers,
            )
        if response.status_code == 503:
            SKIPPED.append("图片检测（模型不可用）")
            print(f"  [跳过] 图片检测：{response.json().get('detail')}")
        else:
            check("图片检测接口", response.status_code == 200, f"HTTP {response.status_code}")
            payload = response.json()
            check("返回检测框", isinstance(payload.get("detections"), list),
                  f"目标数={len(payload.get('detections', []))}")
            check("返回行为统计", len(payload.get("behaviors", [])) == 6, f"{len(payload.get('behaviors', []))} 项")
            check("返回专注度", payload.get("attention", {}).get("formula") is not None,
                  f"score={payload.get('attention', {}).get('score')}")
            check("标注图已保存", bool(payload.get("image_url")), str(payload.get("image_url")))
            check("检测结果写入课堂记录", payload.get("saved") is True)
            detection_info = f"检出 {len(payload.get('detections', []))} 个行为目标，专注度 {payload['attention']['score']}%"

    # 实时课堂：WebSocket 连接 -> 推送一帧 -> 返回检测结果
    image_path = PROJECT_ROOT / "test-file" / "images" / "0001059.jpg"
    if image_path.exists():
        image = imread(image_path)
        section("三、实时课堂（WebSocket）")
        try:
            with client.websocket_connect(f"/ws/classroom/{session['id']}?token={token}") as ws:
                ready = ws.receive_json()
                check("WebSocket 连接成功并返回课堂信息",
                      ready.get("type") == "ready" and ready["session"]["id"] == session["id"])
                check("WebSocket 返回模型状态", "model" in ready)
                ws.send_json({"type": "ping"})
                check("心跳响应", ws.receive_json().get("type") == "pong")
                ws.send_json({"type": "frame", "image": bgr_to_base64(image, quality=70)})
                result = ws.receive_json()
                check("实时帧检测返回结果", result.get("type") == "result", str(result.get("type")))
                check("实时结果包含标注画面", str(result.get("frame", "")).startswith("data:image/jpeg;base64,"))
                check("实时结果包含行为数量", len(result.get("counts", {})) == 6, str(result.get("counts")))
                check("实时结果包含专注度", result.get("attention", {}).get("score") is not None,
                      f"score={result.get('attention', {}).get('score')}")
        except Exception as exc:  # pragma: no cover - WebSocket 测试异常兜底
            check("实时课堂 WebSocket 检测", False, f"{type(exc).__name__}: {exc}")
    else:
        SKIPPED.append("实时课堂（缺少测试图片）")

    response = client.get(f"/api/reports/{session['id']}", headers=headers)
    check("课堂报告接口", response.status_code == 200, f"HTTP {response.status_code}")
    report = response.json()
    check("报告含行为统计字段", "behavior_totals" in report and "summary" in report)
    check("报告含课堂总结", len(report.get("summary", [])) > 0)
    if detection_info:
        check("报告已汇总检测数据", report.get("record_count", 0) > 0,
              f"采样 {report.get('record_count')} 次，平均专注度 {report.get('avg_attention')}%")

    response = client.get(f"/api/reports/{session['id']}/statistics", headers=headers)
    check("报告统计接口", response.status_code == 200 and "attention_series" in response.json())

    # 视频检测：上传短视频 -> 后台任务执行 -> 轮询任务状态
    video_path = PROJECT_ROOT / "test-file" / "vedios" / "aspose_video.mp4"
    section("四、视频检测（后台任务）")
    if not video_path.exists():
        SKIPPED.append("视频检测（缺少测试视频）")
        print(f"  [跳过] 视频检测：测试视频不存在（{video_path}）")
    else:
        with open(video_path, "rb") as fp:
            response = client.post(
                "/api/detection/video",
                files={"file": (video_path.name, fp, "video/mp4")},
                data={"session_id": str(session["id"])},
                headers=headers,
            )
        check("视频检测任务提交", response.status_code == 200, f"HTTP {response.status_code}")
        task_id = response.json().get("task_id")
        status_response = client.get(f"/api/detection/video/{task_id}", headers=headers)
        task = status_response.json()
        check("视频检测任务状态可查询", status_response.status_code == 200)
        check("视频检测任务完成", task.get("status") == "finished", f"status={task.get('status')} {task.get('error') or ''}")
        check("生成结果视频", bool(task.get("result_video_url")), str(task.get("result_video_url")))
        check("视频检测产生专注度数据", task.get("avg_attention") is not None,
              f"处理 {task.get('processed_frames')} 帧，平均专注度 {task.get('avg_attention')}%")

    response = client.post(f"/api/classrooms/{session['id']}/stop", headers=headers)
    check("结束课堂", response.status_code == 200 and response.json()["status"] == "finished")

    check("历史课堂列表", len(client.get("/api/classrooms", headers=headers).json()) == 1)
    check("历史课堂筛选", len(client.get(f"/api/classrooms?course_id={course['id']}", headers=headers).json()) == 1)
    dashboard = client.get("/api/reports/dashboard", headers=headers).json()
    check("首页仪表盘统计", dashboard["course_count"] == 1 and dashboard["session_count"] == 1,
          f"课程 {dashboard['course_count']}，课堂 {dashboard['session_count']}")
    check("系统状态接口", client.get("/api/system/status").json()["model"]["model_exists"] is True)

    check("修改课程", client.put(
        f"/api/courses/{course['id']}", json={"classroom": "实验楼 B210"}, headers=headers
    ).json()["classroom"] == "实验楼 B210")
    check("课程对比接口", client.get(
        f"/api/reports/courses/{course['id']}/compare", headers=headers
    ).status_code == 200)
    check("退出登录", client.post("/api/auth/logout", headers=headers).status_code == 200)
    return {"course_id": course["id"], "session_id": session["id"]}


def test_pages(client: TestClient) -> None:
    section("五、页面与静态资源")
    check("登录页面可访问", client.get("/login").status_code == 200)
    check("未登录访问首页跳转登录页", client.get("/dashboard", follow_redirects=False).status_code == 302)
    check("样式表可访问", client.get("/static/css/style.css").status_code == 200)
    check("图表脚本可访问", client.get("/static/js/charts.js").status_code == 200)
    check("健康检查接口", client.get("/health").json()["status"] == "ok")


def main() -> int:
    print("课堂专注度分析系统 —— 自检开始")
    print(f"项目根目录：{config.BASE_DIR}")
    print(f"临时数据库：{_TEMP_DIR}")

    test_algorithms()
    with TestClient(app) as client:
        test_api_flow(client)
        test_pages(client)

    print("\n=== 自检结果 ===")
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项，跳过 {len(SKIPPED)} 项")
    if FAILED:
        print("失败项：")
        for item in FAILED:
            print(f"  - {item}")
        return 1
    print("全部自检通过 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
