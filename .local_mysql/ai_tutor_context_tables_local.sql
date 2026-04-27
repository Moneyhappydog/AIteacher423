-- AI tutor context tables.
-- Phase 1 adds only new tables and does not modify existing business tables.

CREATE TABLE IF NOT EXISTS ai_tutor_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL UNIQUE,
    group_id INT UNSIGNED NOT NULL,
    member_id VARCHAR(20) NULL,
    page VARCHAR(50) NOT NULL,
    course VARCHAR(50) NOT NULL,
    step_code VARCHAR(50) NULL,
    latest_snapshot JSON NULL,
    latest_diagnosis JSON NULL,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ai_tutor_sessions_group
        FOREIGN KEY (group_id) REFERENCES `groups` (user_id)
        ON DELETE CASCADE,
    INDEX idx_ai_tutor_sessions_group_active (group_id, is_active),
    INDEX idx_ai_tutor_sessions_course_page (course, page)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_tutor_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    group_id INT UNSIGNED NOT NULL,
    member_id VARCHAR(20) NULL,
    page VARCHAR(50) NOT NULL,
    course VARCHAR(50) NOT NULL,
    step_code VARCHAR(50) NULL,
    event_type VARCHAR(50) NOT NULL,
    event_name VARCHAR(100) NOT NULL,
    payload JSON NULL,
    summary_text VARCHAR(255) NULL,
    dedupe_key VARCHAR(120) NULL,
    event_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ai_tutor_events_group
        FOREIGN KEY (group_id) REFERENCES `groups` (user_id)
        ON DELETE CASCADE,
    INDEX idx_ai_tutor_events_session_time (session_id, event_time),
    INDEX idx_ai_tutor_events_group_time (group_id, event_time),
    INDEX idx_ai_tutor_events_name (event_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_tutor_memory_summaries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    group_id INT UNSIGNED NOT NULL,
    summary_type VARCHAR(50) NOT NULL,
    course VARCHAR(50) NULL,
    summary_json JSON NOT NULL,
    window_start DATETIME NULL,
    window_end DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ai_tutor_memory_summaries_group
        FOREIGN KEY (group_id) REFERENCES `groups` (user_id)
        ON DELETE CASCADE,
    INDEX idx_ai_tutor_memory_group_type (group_id, summary_type),
    INDEX idx_ai_tutor_memory_course (course)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_tutor_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    group_id INT UNSIGNED NOT NULL,
    role VARCHAR(20) NOT NULL,
    user_question_text TEXT NULL,
    answer_text TEXT NULL,
    diagnosis VARCHAR(100) NULL,
    next_step VARCHAR(255) NULL,
    tips JSON NULL,
    context_used JSON NULL,
    source VARCHAR(30) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ai_tutor_messages_group
        FOREIGN KEY (group_id) REFERENCES `groups` (user_id)
        ON DELETE CASCADE,
    INDEX idx_ai_tutor_messages_session_time (session_id, created_at),
    INDEX idx_ai_tutor_messages_group_time (group_id, created_at),
    INDEX idx_ai_tutor_messages_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
