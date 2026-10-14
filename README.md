# 基于 Python Web 的课堂专注度分析系统

以原 `class_Detection_end`（YOLOv8 + PyQt5 课堂行为检测）项目的 **YOLOv8 检测成果** 为基础，
把桌面程序重构为 **FastAPI + Web 前端 + 关系型数据库** 的课堂专注度分析系统，
并新增行为统计、专注度计算、课堂管理、实时检测与统计报告等功能。

核心技术：**Python + FastAPI + YOLOv8 + MySQL 8.0（class_detection） + HTML/CSS/JavaScript + WebSocket**

核心算法链：**YOLOv8 课堂行为检测 → 行为统计 → 专注度评价 → 历史分析**

---

## 一、与原项目的区别

| 项目 | 原 PyQt5 桌面程序 | 本系统（Web） |
|---|---|---|
| 界面 | PyQt5 / Qt Designer | HTML + CSS + JavaScript（手写，无 CDN 依赖） |
| 交互 | 桌面窗口 | 浏览器 + HTTP API + WebSocket |
| 后端 | 无 | FastAPI（Router / Service / Model / Schema 分层） |
| 存储 | 保存图片、视频文件 | MySQL 8.0 业务数据库 class_detection（5 张表） |
| 并发 | QThread | FastAPI BackgroundTasks + asyncio + WebSocket |
| 业务能力 | 仅行为检测 | 用户权限、课程、课堂、检测、统计、报告 |
| 专注度 | 无 | 新增专注度算法与专注度趋势分析 |
| 算法 | YOLOv8 课堂行为检测 | **完全沿用**（同一权重、同一 6 类行为） |

## 二、目录结构

```text
class_Detection_end/
├── main.py                 FastAPI 应用入口（页面 + API + 静态资源）
├── config.py               全局配置（模型、数据库、权重、检测参数）
├── requirements.txt        项目依赖（已移除 PyQt5，新增 Web / 数据库依赖）
├── .env.example            环境变量示例（复制为 .env 后填写本机 MySQL 密码）
├── .env                    本机配置（含数据库密码，已在 .gitignore 中排除）
├── .gitignore              忽略 .env、日志、上传、结果、数据库文件等
├── class_detection.sql     MySQL 建库建表脚本（5 张业务表 + 外键索引）
├── 启动服务.bat             一键启动脚本（Windows）
│
├── detection/              【算法层】YOLOv8 检测与专注度计算
│   ├── detector.py         ClassroomDetector：模型加载、推理、检测框解析
│   ├── behavior.py         行为统计（6 类行为数量与平均置信度）
│   ├── attention.py        专注度计算（加权平均公式 + 区间分布）
│   └── image_utils.py      图像读写、检测框绘制、base64 编解码
│
├── database/               【数据层】
│   ├── database.py         连接管理（MySQL；未配置或连接失败时给出明确提示）
│   └── models.py           user / course / class_session / detection_record / attention_record
│
├── schemas/                【校验层】Pydantic 入参与出参模型
├── services/               【服务层】
│   ├── detection_service.py  检测 → 统计 → 专注度 → 落库 的公共流程
│   ├── video_service.py      视频检测后台任务与进度管理
│   ├── report_service.py     历史课堂、统计图表、课堂报告
│   └── security.py           密码哈希（PBKDF2-SHA256）与 JWT 令牌
├── routers/                【接口层】auth / course / classroom / detection / report / pages
├── templates/              【前端页面】login / index / course / classroom / history / report
├── static/                 【前端资源】css / js（含自研 Canvas 图表库）
│
├── models/
│   └── classroom_behavior.pt   课堂行为检测模型（由原项目训练结果复制）
├── datasets/                   原数据集（保留，供重新训练 / 论文实验）
├── training/                   模型训练模块（train.py + data.yaml，路径已修正）
├── runs/                       原训练输出（results.csv、曲线图，供论文实验章节使用）
├── legacy_pyqt5/               已弃用的 PyQt5 桌面程序（保留备查，可随时删除）
├── uploads/                    上传的原始图片 / 视频
├── results/                    检测结果图与结果视频（通过 /results/ 访问）
├── logs/                       运行日志（app.log）
└── tests/
    ├── self_check.py           系统功能自检（隔离数据库，验证全部业务功能）
    ├── check_mysql.py          MySQL 接入验证（连接、表结构、业务链路落库）
    ├── test_cases.py           测试用例表（U01~U11、C01~C08，输出 docs/测试用例表.md）
    ├── test_permissions.py     权限数据隔离测试（输出 docs/权限隔离测试.md）
    └── attention_experiment.py 专注度权重对比实验（输出 docs/专注度权重实验结果.md）
├── tools/
    ├── migrate_schema.py       数据库结构升级（为已有库补充字段与索引，可重复执行）
    └── model_metrics.py        YOLOv8 指标整理与测试集评估（输出 docs/模型评估指标.md）
```

## 三、环境准备与启动

### 0. 关于仓库中不包含的文件

为控制仓库体积，GitHub 上只保留**源代码、配置、页面与文档**，以下本机文件已通过 `.gitignore` 排除：

| 排除内容 | 原因 | 本地如何恢复 |
|---|---|---|
| `models/classroom_behavior.pt`、`*.pt` | 模型权重约 6 MB | 训练得到，或从 `runs/v8-4-pose-all2/weights/best.pt` 复制 |
| `datasets/` | 课堂行为数据集约 509 MB | 按 `training/data.yaml` 放置数据集 |
| `runs/` | YOLOv8 训练输出约 112 MB | 执行 `training/train.py` 重新训练，或保留本地副本（论文实验图表） |
| `test-file/`、`TestFiles/` | 测试图片与视频素材 | 自备课堂图片 / 视频 |
| `Font/platech.ttf` | 中文字体 14 MB | 非必需，程序会自动改用系统字体（微软雅黑等） |
| `.env`、``*.db`` | 本机数据库密码与数据 | 复制 `.env.example` 重新配置 |
| `uploads/`、`results/`、`logs/` | 运行期生成 | 由程序自动创建 |

因此克隆仓库后运行检测功能前，需要先把模型权重放到 `models/classroom_behavior.pt`。
没有测试素材时，`tests/test_cases.py`、`tests/test_permissions.py`、`tests/self_check.py`
会自动跳过依赖图片 / 视频的用例，其余功能检查照常执行。

### 1. 安装依赖

```powershell
# 已内置虚拟环境 .venv（Python 3.12），首次使用可直接安装依赖：
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 也可以使用自己的 Python 环境：
pip install -r requirements.txt
```

### 2. 启动服务

```powershell
# 方式一：一键启动（推荐）
双击 启动服务.bat

# 方式二：命令行
.venv\Scripts\python.exe main.py

# 方式三：uvicorn
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

浏览器访问 <http://127.0.0.1:8000>，默认管理员账号：

| 账号 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | 管理员 |

### 3. 运行自检（验证环境是否正常）

```powershell
# 功能自检（使用临时数据库，不影响正式数据）
.venv\Scripts\python.exe tests\self_check.py

# MySQL 接入验证（确认真正连上 class_detection，并验证数据落库链路）
.venv\Scripts\python.exe tests\check_mysql.py

# 系统测试用例表（论文"系统测试"章节素材）
.venv\Scripts\python.exe tests\test_cases.py

# 权限数据隔离测试
.venv\Scripts\python.exe tests\test_permissions.py

# 专注度权重对比实验（论文"算法实验"章节素材）
.venv\Scripts\python.exe tests\attention_experiment.py

# YOLOv8 模型指标整理（加 --val 会重新在测试集上评估一次）
.venv\Scripts\python.exe tools\model_metrics.py --val
```

自检脚本会自动完成：登录认证 → 课程管理 → 课堂开始/结束 → YOLOv8 图片检测 →
WebSocket 实时检测 → 视频检测后台任务 → 课堂报告与统计 → 页面与静态资源检查，
并输出「通过 / 失败 / 跳过」统计。

## 四、数据库配置

系统使用 **MySQL 8.0** 数据库 `class_detection`。连接串不在代码中硬编码，
必须通过项目根目录的 `.env` 配置（该文件已被 `.gitignore` 排除，不会提交到代码仓库）：

```text
mysql+pymysql://<用户名>:<密码>@127.0.0.1:3306/class_detection?charset=utf8mb4
```

### 首次部署步骤

1. 启动 MySQL 服务（MySQL 8.0），执行项目根目录的建库建表脚本：

```powershell
mysql -u root -p -e "source D:/class_Detection_end/class_detection.sql"
```

2. 复制 `.env.example` 为 `.env`，填写本机 MySQL 密码：

```ini
CLASSROOM_DB_URL=mysql+pymysql://root:<你的MySQL密码>@127.0.0.1:3306/class_detection?charset=utf8mb4
CLASSROOM_SQLITE_FALLBACK=0
```

3. 运行 `tests/check_mysql.py` 确认输出 `dialect: mysql`、`fallback_to_sqlite: false`；
   也可以启动服务后访问 `/api/system/status` 查看同样的信息。

说明：`CLASSROOM_SQLITE_FALLBACK=0` 表示 MySQL 不可用时系统直接报错并给出配置提示，
不会静默切换到 SQLite。只有本机临时没有 MySQL 时，才把它设为 `1`，此时系统会使用
项目根目录的 `classroom_attention.db`（旧文件已备份为 `classroom_attention.db.bak`）。

5 张业务表结构（由 `class_detection.sql` 创建，与 SQLAlchemy 模型一一对应）：

| 数据表 | 说明 | 主要字段 |
|---|---|---|
| user | 用户 | id, username, password, real_name, role, status, create_time, update_time, last_login_time |
| course | 课程 | id, course_name, teacher_id, class_name, classroom, description, create_time |
| class_session | 课堂记录 | id, course_id, start_time, end_time, duration, status, analysis_mode, video_path, result_video_path, created_by |
| detection_record | 行为检测记录 | id, session_id, behavior_type, person_count, avg_confidence, frame_index, detection_time |
| attention_record | 专注度记录 | id, session_id, student_count, focused_count, unfocused_count, attention_score, confidence_threshold, record_time |

已有数据库升级：执行 `python tools/migrate_schema.py`（按 information_schema 检查后补建字段与索引，可重复执行）。

## 五、功能模块

| 模块 | 页面 | 说明 |
|---|---|---|
| 用户管理 | /login | 登录、退出、JWT + HttpOnly Cookie、角色权限（管理员 / 教师） |
| 用户管理 | /users | 仅管理员：用户列表、创建账号、修改姓名 / 角色、禁用或启用、重置密码、删除 |
| 个人中心 | /profile | 查看账号信息、修改姓名、修改密码 |
| 首页概览 | /dashboard | 课程数、课堂数、今日课堂、平均专注度、最近课堂与趋势 |
| 课程管理 | /courses | 课程增删改查、班级与教室信息、平均专注度 |
| 课堂检测 | /classroom | 开始 / 结束课堂；图片检测、视频检测、实时课堂三种方式 |
| 历史课堂 | /history | 历史课堂筛选、平均 / 最高 / 最低专注度、课程专注度对比 |
| 课堂报告 | /report/{id} | 平均 / 最高 / 最低专注度、行为统计、趋势图、比例图、区间分布、课堂总结、打印导出 PDF |

## 六、API 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/auth/login | 登录（返回 JWT 并写入 Cookie，支持 remember_me 记住登录状态） |
| POST | /api/auth/logout | 退出登录 |
| GET | /api/auth/me | 当前登录用户 |
| PUT | /api/auth/me | 修改当前用户姓名 |
| POST | /api/auth/password | 修改密码 |
| GET / POST | /api/auth/users | 用户列表 / 创建用户（管理员） |
| PUT / DELETE | /api/auth/users/{id} | 修改姓名、角色、启用或禁用 / 删除用户（管理员） |
| POST | /api/auth/users/{id}/reset-password | 重置用户密码（管理员） |
| GET/POST | /api/courses | 课程列表 / 新建课程 |
| GET/PUT/DELETE | /api/courses/{id} | 课程详情 / 修改 / 删除 |
| POST | /api/classrooms/start | 开始一次课堂 |
| POST | /api/classrooms/{id}/stop | 结束课堂 |
| GET | /api/classrooms | 课堂列表（支持 course_id、status_filter 过滤） |
| GET | /api/classrooms/{id} | 课堂详情（含行为统计与专注度序列） |
| GET | /api/classrooms/{id}/records | 课堂检测明细记录 |
| DELETE | /api/classrooms/{id} | 删除课堂记录 |
| POST | /api/detection/image | 图片课堂行为检测 |
| POST | /api/detection/video | 提交视频检测后台任务 |
| GET | /api/detection/video/{task_id} | 查询视频检测进度与结果 |
| WS | /ws/classroom/{session_id} | 实时课堂检测（WebSocket） |
| WS | /ws/ping | 实时检测服务连通性探测（首页状态显示用） |
| GET | /api/reports/dashboard | 首页仪表盘统计 |
| GET | /api/reports/{session_id} | 课堂分析报告 |
| GET | /api/reports/{session_id}/statistics | 图表统计数据 |
| GET | /api/reports/courses/{course_id}/compare | 同一课程多次课堂对比 |
| GET | /api/system/status | 系统 / 模型 / 数据库状态 |

接口文档（Swagger UI）：<http://127.0.0.1:8000/docs>

## 七、专注度算法

```text
        A = Σ(N_i × W_i) / Σ(N_i) × 100%
```

其中 `N_i` 为第 i 类行为的人数，`W_i` 为该行为的专注度权重，`A` 为课堂专注度。

| 行为 | 权重 | 分类 |
|---|---:|---|
| 举手 hand-raising | 1.0 | 专注 |
| 阅读 reading | 1.0 | 专注 |
| 写作 writing | 1.0 | 专注 |
| 使用手机 using phone | 0.0 | 非专注 |
| 低头 bowing the head | 0.3 | 非专注 |
| 趴在桌上 leaning over the table | 0.2 | 非专注 |

专注度评价区间：≥90% 非常专注、≥80% 比较专注、≥70% 中等水平、≥60% 偏低、<60% 不专注。

> 权重属于系统设计的初始参数，可在 `config.py` 的 `ATTENTION_WEIGHTS` 中调整；
> 论文中建议通过实验对比或专家意见对其进行说明与验证，不宜直接宣称是通用标准。

## 八、实时课堂（WebSocket）

`ws://<host>/ws/classroom/{session_id}`，支持三种视频来源：

1. **浏览器摄像头**：前端通过 `getUserMedia` 采集画面，压缩为 JPEG 后逐帧发送；
2. **服务器本机摄像头**：前端发送 `{"type":"start_camera","device":0}`，由服务端读取摄像头；
3. **本地视频文件**：前端播放本地视频并逐帧发送（适合无摄像头的演示环境）。

服务端返回结构示例：

```json
{
  "type": "result",
  "time": "14:25:31",
  "student_count": 35,
  "attention_score": 83.6,
  "counts": {
    "hand_raising": 2, "reading": 8, "writing": 15,
    "using_phone": 3, "bowing_head": 5, "leaning_over_table": 2
  },
  "attention": { "score": 83.6, "level": "比较专注" },
  "frame": "data:image/jpeg;base64,..."
}
```

检测结果默认每 5 秒写入一次数据库（`CLASSROOM_REALTIME_RECORD_INTERVAL`），
避免数据库写入过于频繁。

## 九、常见问题

| 现象 | 原因与处理 |
|---|---|
| 启动时提示「[启动失败] MySQL 连接失败…」 | 本机 MySQL 未启动、数据库未创建或 `.env` 中密码不正确；按提示检查 `class_detection.sql` 与 `.env` |
| 启动时提示「[启动失败] 未配置数据库连接」 | 项目根目录缺少 `.env`；复制 `.env.example` 并填写 `CLASSROOM_DB_URL` |
| 需要临时脱离 MySQL 演示 | 在 `.env` 中把 `CLASSROOM_SQLITE_FALLBACK` 设为 `1`，系统会改用本地 SQLite 文件 |
| 检测接口返回 503「YOLOv8 依赖未安装」 | 未安装 ultralytics / torch，执行 `pip install -r requirements.txt` |
| 页面提示「模型文件缺失」 | `models/classroom_behavior.pt` 不存在，可从 `runs/v8-4-pose-all2/weights/best.pt` 复制 |
| 浏览器摄像头无法打开 | 需使用 `http://127.0.0.1` 或 `https` 访问；并在浏览器中允许摄像头权限 |
| 服务器摄像头模式报错 | 服务器（本机）没有可用摄像头，改用「浏览器摄像头」或「本地视频文件」 |
| 视频检测耗时较长 | 视频是逐帧处理且 CPU 推理，可通过调大 `CLASSROOM_VIDEO_INTERVAL` 降低检测频率 |

## 十、可复用于论文的素材

* 模型训练与评估结果：`runs/v8-4-pose-all2/`（results.csv、P/R/mAP 曲线、混淆矩阵、PR 曲线）
* 系统功能截图：登录、首页、课程管理、课堂检测（图片 / 视频 / 实时）、历史课堂、课堂报告
* 算法说明：行为统计与专注度计算公式（`detection/attention.py`）
* 数据库设计：5 张业务表（`database/models.py`）
* 数据库脚本：`class_detection.sql`（建库、建表、外键与索引）
* 界面设计：顶部标题栏 + 左侧菜单 + 面板式内容区（浅色、低饱和度、无第三方 UI 库依赖），
  图表由原生 Canvas 绘制（`static/css/style.css`、`static/js/charts.js`）
* 系统架构：Web 前端 → FastAPI → 检测服务 → 专注度算法 → 数据库
* 自检结果：`tests/self_check.py`（功能）与 `tests/check_mysql.py`（数据库）的输出结论
