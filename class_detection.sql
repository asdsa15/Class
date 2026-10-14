-- =========================================================
-- 基于 Python Web 的课堂专注度分析系统 —— MySQL 数据库脚本
--
-- 数据库：class_detection（MySQL 8.0，utf8mb4 / utf8mb4_unicode_ci）
-- 说明：本脚本按《class_Detection_end 项目完整检查与 MySQL 改造报告》
--       第 6 节提供的结构编写，5 张业务表与 SQLAlchemy 模型
--       （database/models.py）保持一致。
--
-- 执行方式（任选其一）：
--   1) mysql -u root -p -e "source D:/class_Detection_end/class_detection.sql"
--   2) 在 MySQL 客户端中执行：SOURCE D:/class_Detection_end/class_detection.sql;
--
-- 注意：脚本会先删除同名表（仅限 class_detection 库），请勿在有重要数据时重跑。
-- =========================================================

CREATE DATABASE IF NOT EXISTS class_detection
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE class_detection;

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS attention_record;
DROP TABLE IF EXISTS detection_record;
DROP TABLE IF EXISTS class_session;
DROP TABLE IF EXISTS course;
DROP TABLE IF EXISTS user;

SET FOREIGN_KEY_CHECKS = 1;


-- =========================================================
-- 1. 用户表：登录、角色权限（admin / teacher）
-- =========================================================
CREATE TABLE user (
    id INT NOT NULL AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    real_name VARCHAR(50) NOT NULL DEFAULT '',
    role VARCHAR(20) NOT NULL DEFAULT 'teacher',
    status INT NOT NULL DEFAULT 1 COMMENT '账号状态：1 正常 / 0 已禁用',
    create_time DATETIME NOT NULL,
    update_time DATETIME NULL COMMENT '最近更新时间',
    last_login_time DATETIME NULL COMMENT '最近登录时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_username (username),
    KEY ix_user_username (username)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 2. 课程表：课程名称、授课教师、班级、教室
-- =========================================================
CREATE TABLE course (
    id INT NOT NULL AUTO_INCREMENT,
    course_name VARCHAR(100) NOT NULL,
    teacher_id INT NOT NULL,
    class_name VARCHAR(50) NOT NULL DEFAULT '',
    classroom VARCHAR(50) NOT NULL DEFAULT '',
    description TEXT,
    create_time DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_course_teacher_id (teacher_id),
    CONSTRAINT fk_course_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES user(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 3. 课堂记录表：一次完整课堂检测（开始 / 结束 / 时长 / 状态）
-- =========================================================
CREATE TABLE class_session (
    id INT NOT NULL AUTO_INCREMENT,
    course_id INT NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NULL,
    duration INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    analysis_mode VARCHAR(20) NOT NULL DEFAULT '' COMMENT '分析方式：image / video / realtime',
    video_path VARCHAR(255) NOT NULL DEFAULT '' COMMENT '原始视频路径',
    result_video_path VARCHAR(255) NOT NULL DEFAULT '' COMMENT '结果视频路径',
    created_by INT NULL COMMENT '创建人用户ID',
    PRIMARY KEY (id),
    KEY ix_class_session_course_id (course_id),
    KEY ix_class_session_status (status),
    KEY ix_session_course_status_time (course_id, status, start_time),
    CONSTRAINT fk_class_session_course
        FOREIGN KEY (course_id)
        REFERENCES course(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 4. YOLOv8 行为检测记录表：某时刻某类行为的人数与平均置信度
-- =========================================================
CREATE TABLE detection_record (
    id INT NOT NULL AUTO_INCREMENT,
    session_id INT NOT NULL,
    behavior_type VARCHAR(30) NOT NULL,
    person_count INT NOT NULL DEFAULT 0,
    avg_confidence FLOAT NOT NULL DEFAULT 0,
    frame_index INT NOT NULL DEFAULT 0,
    detection_time DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_detection_record_session_id (session_id),
    KEY ix_detection_record_detection_time (detection_time),
    KEY ix_detection_session_behavior (session_id, behavior_type),
    KEY ix_detection_session_behavior_time (session_id, behavior_type, detection_time),
    CONSTRAINT fk_detection_record_session
        FOREIGN KEY (session_id)
        REFERENCES class_session(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 5. 专注度记录表：学生人数、专注 / 不专注人数、专注度
-- =========================================================
CREATE TABLE attention_record (
    id INT NOT NULL AUTO_INCREMENT,
    session_id INT NOT NULL,
    student_count INT NOT NULL DEFAULT 0,
    focused_count INT NOT NULL DEFAULT 0,
    unfocused_count INT NOT NULL DEFAULT 0,
    attention_score FLOAT NOT NULL DEFAULT 0,
    confidence_threshold FLOAT NOT NULL DEFAULT 0 COMMENT '本次检测使用的置信度阈值',
    record_time DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_attention_record_session_id (session_id),
    KEY ix_attention_record_record_time (record_time),
    KEY ix_attention_session_time (session_id, record_time),
    CONSTRAINT fk_attention_record_session
        FOREIGN KEY (session_id)
        REFERENCES class_session(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- 初始化管理员说明
--
-- 项目使用 PBKDF2-SHA256 校验密码，不能直接插入明文密码。
-- 首次启动时 database/database.py 的 _create_default_admin()
-- 会自动创建管理员：
--     用户名：admin
--     密码：admin123
-- 正式使用时请登录后立即修改密码。
-- =========================================================


-- =========================================================
-- 结构检查
-- =========================================================
SHOW TABLES;

SELECT DATABASE();

DESCRIBE user;
DESCRIBE course;
DESCRIBE class_session;
DESCRIBE detection_record;
DESCRIBE attention_record;
