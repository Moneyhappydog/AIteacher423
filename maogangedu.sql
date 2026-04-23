-- ============================================================
--  maogangedu.sql  — 编程猫 × 香港科技大学（广州）联合实验室教学平台
--  适用版本：MySQL 8.0+
--  数据库名：maogang
-- ============================================================

CREATE DATABASE IF NOT EXISTS `maogang`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `maogang`;

-- -------------------------------------------------------
-- 1.  用户表（超级管理员 / 教师 / 学生小组）
-- -------------------------------------------------------
CREATE TABLE `users` (
    `id`           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `username`     VARCHAR(50)      NOT NULL UNIQUE COMMENT '登录用户名',
    `password_hash` VARCHAR(255)   NOT NULL COMMENT 'bcrypt 加密密码',
    `display_name` VARCHAR(100)     NOT NULL COMMENT '展示名称（管理员名/小组名）',
    `role`         ENUM('super_admin','teacher','group') NOT NULL COMMENT '角色：超级管理员/教师/学生小组',
    `avatar`       VARCHAR(255)     DEFAULT NULL COMMENT '头像路径（可为NULL）',
    `created_at`   DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`   DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `is_active`    TINYINT(1)       NOT NULL DEFAULT 1 COMMENT '1=启用，0=禁用',
    `remark`       TEXT             DEFAULT NULL COMMENT '备注（如小组编号、所属课程等）',
    INDEX `idx_role`        (`role`),
    INDEX `idx_is_active`  (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表：超级管理员、教师、学生小组';

-- -------------------------------------------------------
-- 2.  学生小组扩展信息表
-- -------------------------------------------------------
CREATE TABLE `groups` (
    `id`              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `user_id`         INT UNSIGNED NOT NULL UNIQUE COMMENT '关联 users.id（一对一）',
    `group_code`      VARCHAR(10)   NOT NULL UNIQUE COMMENT '小组编号，如 G01、G02',
    `course`          VARCHAR(50)   DEFAULT NULL COMMENT '所属课程标识，如 emotion/ecobottle',
    `member_count`    INT UNSIGNED  NOT NULL DEFAULT 1 COMMENT '小组成员人数',
    `experience`      INT UNSIGNED  NOT NULL DEFAULT 0 COMMENT '经验值（技能树）',
    `skill_tree`      JSON          DEFAULT NULL COMMENT '技能树进度 JSON',
    `last_active_at`  DATETIME      DEFAULT NULL COMMENT '最后活跃时间',
    `created_at`      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_group_code` (`group_code`),
    INDEX `idx_course`     (`course`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生小组扩展信息';

-- -------------------------------------------------------
-- 3.  排行榜记录表
-- -------------------------------------------------------
CREATE TABLE `leaderboard_records` (
    `id`                INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `group_id`          INT UNSIGNED NOT NULL COMMENT '提交小组（关联 groups.user_id）',
    `course`            VARCHAR(30)  NOT NULL COMMENT '课程标识：face_emotion / audio_emotion / fusion / ecobottle',
    `accuracy`          DECIMAL(6,4) NOT NULL COMMENT '准确率（0.0000 - 1.0000）',
    `correct_count`     INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '正确数',
    `total_count`       INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '测试集总数',
    `time_cost_seconds` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '训练耗时（秒）',
    `model_file`        VARCHAR(255) NOT NULL COMMENT '提交的模型文件名',
    `model_config`      JSON         DEFAULT NULL COMMENT '模型超参数配置',
    `composite_score`   DECIMAL(6,2) DEFAULT NULL COMMENT '综合得分（null 时由系统计算）',
    `innovation_score`  INT UNSIGNED DEFAULT NULL COMMENT '创新得分（教师评）',
    `awards`            JSON         DEFAULT NULL COMMENT '徽章/称号列表',
    `is_public`         TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '1=公开到排行榜，0=草稿',
    `submitted_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`user_id`) ON DELETE CASCADE,
    INDEX `idx_course_public`  (`course`, `is_public`),
    INDEX `idx_submitted_at`  (`submitted_at`),
    INDEX `idx_accuracy`       (`accuracy` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='排行榜提交记录';

-- -------------------------------------------------------
-- 4.  表情数据集表（训练集 / 测试集 元数据）
-- -------------------------------------------------------
CREATE TABLE `face_datasets` (
    `id`            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `group_id`      INT UNSIGNED NOT NULL COMMENT '所属小组',
    `file_path`     VARCHAR(500) NOT NULL COMMENT '图片文件相对路径（不含前缀）',
    `file_name`     VARCHAR(200) NOT NULL COMMENT '原始文件名',
    `label`         VARCHAR(20)  NOT NULL COMMENT '标注标签：happy / sad / angry / surprised / fearful / disgusted / neutral',
    `label_source`  ENUM('ai_auto','teacher','group') NOT NULL DEFAULT 'ai_auto' COMMENT '标注来源',
    `confidence`    DECIMAL(5,4) DEFAULT NULL COMMENT 'AI预测置信度',
    `dataset_type`  ENUM('train','test') NOT NULL COMMENT '数据集类型',
    `status`        ENUM('pending','confirmed','rejected') NOT NULL DEFAULT 'pending' COMMENT '标注审核状态',
    `reviewed_by`   INT UNSIGNED DEFAULT NULL COMMENT '审核人 user_id（教师）',
    `reviewed_at`   DATETIME     DEFAULT NULL COMMENT '审核时间',
    `uploaded_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`group_id`)  REFERENCES `groups`(`user_id`) ON DELETE CASCADE,
    FOREIGN KEY (`reviewed_by`) REFERENCES `users`(`id`) ON DELETE SET NULL,
    INDEX `idx_group_type`   (`group_id`, `dataset_type`),
    INDEX `idx_label_status` (`label`, `status`),
    INDEX `idx_uploaded_at`  (`uploaded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='表情数据集元数据';

-- -------------------------------------------------------
-- 5.  声音数据集表
-- -------------------------------------------------------
CREATE TABLE `audio_datasets` (
    `id`            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `group_id`      INT UNSIGNED NOT NULL COMMENT '所属小组',
    `file_path`     VARCHAR(500) NOT NULL COMMENT '音频文件相对路径',
    `file_name`     VARCHAR(200) NOT NULL COMMENT '原始文件名',
    `duration_sec`  DECIMAL(6,2) DEFAULT NULL COMMENT '音频时长（秒）',
    `label`         VARCHAR(20)  NOT NULL COMMENT '标注标签：angry / fearful / happy / neutral / sad / surprised',
    `label_source`  ENUM('ai_auto','teacher','group') NOT NULL DEFAULT 'ai_auto',
    `confidence`    DECIMAL(5,4) DEFAULT NULL,
    `dataset_type`  ENUM('train','test') NOT NULL,
    `status`        ENUM('pending','confirmed','rejected') NOT NULL DEFAULT 'pending',
    `reviewed_by`   INT UNSIGNED DEFAULT NULL,
    `reviewed_at`   DATETIME     DEFAULT NULL,
    `uploaded_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`group_id`)  REFERENCES `groups`(`user_id`) ON DELETE CASCADE,
    FOREIGN KEY (`reviewed_by`) REFERENCES `users`(`id`) ON DELETE SET NULL,
    INDEX `idx_group_type`   (`group_id`, `dataset_type`),
    INDEX `idx_label_status` (`label`, `status`),
    INDEX `idx_uploaded_at`  (`uploaded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='声音数据集元数据';

-- -------------------------------------------------------
-- 6.  传感器/生态瓶数据集表
-- -------------------------------------------------------
CREATE TABLE `ecobottle_datasets` (
    `id`            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `group_id`      INT UNSIGNED NOT NULL COMMENT '所属小组',
    `file_path`     VARCHAR(500) NOT NULL COMMENT 'CSV 文件相对路径',
    `file_name`     VARCHAR(200) NOT NULL COMMENT '文件名',
    `record_count`  INT UNSIGNED  NOT NULL DEFAULT 0 COMMENT '记录条数',
    `feature_cols`  JSON          DEFAULT NULL COMMENT '特征列名列表',
    `target_col`    VARCHAR(50)   DEFAULT NULL COMMENT '目标列名',
    `dataset_type`  ENUM('train','test') NOT NULL,
    `status`        ENUM('pending','confirmed','rejected') NOT NULL DEFAULT 'pending',
    `reviewed_by`   INT UNSIGNED  DEFAULT NULL,
    `reviewed_at`   DATETIME      DEFAULT NULL,
    `uploaded_at`   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`group_id`)  REFERENCES `groups`(`user_id`) ON DELETE CASCADE,
    FOREIGN KEY (`reviewed_by`) REFERENCES `users`(`id`) ON DELETE SET NULL,
    INDEX `idx_group_type`   (`group_id`, `dataset_type`),
    INDEX `idx_uploaded_at`  (`uploaded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='生态瓶/传感器数据集元数据';

-- -------------------------------------------------------
-- 7.  模型文件表
-- -------------------------------------------------------
CREATE TABLE `model_files` (
    `id`             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `group_id`       INT UNSIGNED NOT NULL COMMENT '所属小组',
    `course`         VARCHAR(30)  NOT NULL COMMENT '所属课程',
    `model_name`     VARCHAR(200) NOT NULL COMMENT '模型展示名称',
    `file_path`      VARCHAR(500) NOT NULL COMMENT '模型文件相对路径',
    `file_size_bytes` BIGINT UNSIGNED DEFAULT NULL COMMENT '文件大小（字节）',
    `model_type`     VARCHAR(50)  DEFAULT NULL COMMENT '模型类型：cnn / transformer / polynomial / prophet / arima / lightgbm',
    `config`         JSON          DEFAULT NULL COMMENT '训练超参数',
    `accuracy`       DECIMAL(6,4) DEFAULT NULL COMMENT '该模型在测试集上的准确率',
    `metrics`        JSON          DEFAULT NULL COMMENT '其他指标（R² / RMSE / MAE 等）',
    `is_pretrained`  TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '1=系统预训练模型，0=小组自训练',
    `is_active`      TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用（可被选为提交模型）',
    `created_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`user_id`) ON DELETE CASCADE,
    INDEX `idx_course_pretrained` (`course`, `is_pretrained`),
    INDEX `idx_group_active`      (`group_id`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型文件表';

-- -------------------------------------------------------
-- 8.  代码笔记本表（编辑器中保存的 .py 文件）
-- -------------------------------------------------------
CREATE TABLE `notebooks` (
    `id`         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `group_id`   INT UNSIGNED NOT NULL COMMENT '所属小组',
    `course`     VARCHAR(30)  NOT NULL COMMENT '所属课程',
    `file_name`  VARCHAR(200) NOT NULL COMMENT '文件名（含扩展名）',
    `file_path`  VARCHAR(500) NOT NULL COMMENT '文件存储相对路径',
    `content`    LONGTEXT     DEFAULT NULL COMMENT '文件内容快照（可为空，优先读文件系统）',
    `language`   VARCHAR(20)   NOT NULL DEFAULT 'python',
    `version`    INT UNSIGNED  NOT NULL DEFAULT 1 COMMENT '版本号',
    `is_template` TINYINT(1)  NOT NULL DEFAULT 0 COMMENT '1=系统预置模板',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`user_id`) ON DELETE CASCADE,
    UNIQUE KEY `uk_group_filename` (`group_id`, `file_name`),
    INDEX `idx_course_template` (`course`, `is_template`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='代码笔记本/脚本表';

-- -------------------------------------------------------
-- 9.  操作审计日志表
-- -------------------------------------------------------
CREATE TABLE `audit_logs` (
    `id`         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `user_id`    INT UNSIGNED NOT NULL COMMENT '操作用户',
    `action`     VARCHAR(50)  NOT NULL COMMENT '操作类型：LOGIN / LOGOUT / SUBMIT_LEADERBOARD / UPLOAD_DATA / TRAIN_MODEL 等',
    `target_type` VARCHAR(50) DEFAULT NULL COMMENT '操作对象类型',
    `target_id`  VARCHAR(100) DEFAULT NULL COMMENT '操作对象ID',
    `detail`     JSON          DEFAULT NULL COMMENT '操作详情',
    `ip_address` VARCHAR(45)  DEFAULT NULL COMMENT '客户端 IP',
    `user_agent` VARCHAR(500) DEFAULT NULL COMMENT '浏览器 UA',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_created` (`user_id`, `created_at` DESC),
    INDEX `idx_action`       (`action`),
    INDEX `idx_created_at`   (`created_at` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='操作审计日志';

-- -------------------------------------------------------
-- 10.  技能树进度表
-- -------------------------------------------------------
CREATE TABLE `skill_progress` (
    `id`          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `group_id`    INT UNSIGNED NOT NULL UNIQUE COMMENT '所属小组（每个小组一条）',
    `skills`      JSON         NOT NULL COMMENT '技能树进度 JSON',
    `total_xp`    INT UNSIGNED  NOT NULL DEFAULT 0 COMMENT '总经验值',
    `updated_at`  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='技能树进度表';

-- -------------------------------------------------------
-- 11.  系统公告 / 活动消息表
-- -------------------------------------------------------
CREATE TABLE `announcements` (
    `id`         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `title`      VARCHAR(200) NOT NULL,
    `content`    TEXT         NOT NULL,
    `priority`   ENUM('normal','important','urgent') NOT NULL DEFAULT 'normal',
    `target_role` ENUM('all','teacher','group') NOT NULL DEFAULT 'all' COMMENT '可见范围',
    `course`     VARCHAR(30)  DEFAULT NULL COMMENT '关联课程（null=全局公告）',
    `published_by` INT UNSIGNED NOT NULL COMMENT '发布人（教师或超管）',
    `is_pinned`  TINYINT(1)   NOT NULL DEFAULT 0,
    `is_active`  TINYINT(1)   NOT NULL DEFAULT 1,
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`published_by`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_target_role` (`target_role`),
    INDEX `idx_course`      (`course`),
    INDEX `idx_pinned`      (`is_pinned`, `created_at` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统公告表';

-- ============================================================
--  初始化数据
-- ============================================================

-- 超级管理员
INSERT INTO `users` (`username`, `password_hash`, `display_name`, `role`, `remark`)
VALUES
    ('admin', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '系统管理员', 'super_admin', '系统超级管理员，拥有全部权限');

-- 教师账号
INSERT INTO `users` (`username`, `password_hash`, `display_name`, `role`, `remark`)
VALUES
    ('teacher_zhangsan', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '老师1', 'teacher', '教师1，密码：Maogang@2026'),
    ('teacher_maocat', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '老师2', 'teacher', '教师2，密码：Maogang@2026');

-- 学生小组账号
INSERT INTO `users` (`username`, `password_hash`, `display_name`, `role`, `remark`)
VALUES
    ('G01', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第1组', 'group', '课程小组，密码：Maogang@2026'),
    ('G02', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第2组', 'group', '课程小组，密码：Maogang@2026'),
    ('G03', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第3组', 'group', '课程小组，密码：Maogang@2026'),
    ('G04', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第4组', 'group', '课程小组，密码：Maogang@2026'),
    ('G05', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第5组', 'group', '课程小组，密码：Maogang@2026'),
    ('G06', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第6组', 'group', '课程小组，密码：Maogang@2026'),
    ('G07', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第7组', 'group', '课程小组，密码：Maogang@2026'),
    ('G08', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第8组', 'group', '课程小组，密码：Maogang@2026'),
    ('G09', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第9组', 'group', '课程小组，密码：Maogang@2026'),
    ('G10', 'scrypt:32768:8:1$9SyDsPYe5mNjgFDT$88b4ffc9e1dc1f9c668239683106de6ed706f615c6a4c52a8897640c6f18be06bfc6d6227df7c23d6ce791d0bda239fa512b538b6c7a927689f4c56be19b016d', '第10组', 'group', '课程小组，密码：Maogang@2026');

-- 小组扩展信息（小组可使用所有课程模块，不再限制 course 字段）
INSERT INTO `groups` (`user_id`, `group_code`, `member_count`, `experience`, `skill_tree`)
VALUES
    (4, 'G01', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (5, 'G02', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (6, 'G03', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (7, 'G04', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (8, 'G05', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (9, 'G06', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (10, 'G07', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (11, 'G08', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (12, 'G09', 6, 0, '{"data": 0, "algo": 0, "ai": 0}'),
    (13, 'G10', 6, 0, '{"data": 0, "algo": 0, "ai": 0}');
CREATE OR REPLACE VIEW `v_leaderboard_public` AS
SELECT
    lbr.id,
    lbr.course,
    lbr.accuracy,
    lbr.correct_count,
    lbr.total_count,
    lbr.time_cost_seconds,
    lbr.model_file,
    lbr.composite_score,
    lbr.submitted_at,
    g.group_code,
    u.display_name AS group_name,
    ROW_NUMBER() OVER (
        PARTITION BY lbr.course, DATE(lbr.submitted_at)
        ORDER BY lbr.accuracy DESC, lbr.time_cost_seconds ASC
    ) AS daily_rank
FROM leaderboard_records lbr
JOIN groups g ON lbr.group_id = g.user_id
JOIN users u ON g.user_id = u.id
WHERE lbr.is_public = 1
ORDER BY lbr.course, lbr.accuracy DESC;

-- -------------------------------------------------------
-- 视图：小组总览（含排行榜最新成绩）
-- -------------------------------------------------------
CREATE OR REPLACE VIEW `v_groups_overview` AS
SELECT
    g.id               AS group_id,
    g.group_code,
    u.display_name     AS group_name,
    u.is_active,
    g.member_count,
    g.experience,
    g.course,
    g.last_active_at,
    (
        SELECT lbr.accuracy
        FROM leaderboard_records lbr
        WHERE lbr.group_id = g.user_id AND lbr.is_public = 1
        ORDER BY lbr.submitted_at DESC
        LIMIT 1
    ) AS latest_accuracy,
    (
        SELECT lbr.course
        FROM leaderboard_records lbr
        WHERE lbr.group_id = g.user_id AND lbr.is_public = 1
        ORDER BY lbr.submitted_at DESC
        LIMIT 1
    ) AS latest_course
FROM groups g
JOIN users u ON g.user_id = u.id
ORDER BY g.group_code;

-- ============================================================
--  测试账号密码说明：
--  所有账号密码均为真实 bcrypt hash，部署后直接可用。
--  如需修改密码，执行：
--  from werkzeug.security import generate_password_hash
--  hash = generate_password_hash('NewPassword')
--  UPDATE users SET password_hash = hash WHERE username = 'xxx';
-- ============================================================
