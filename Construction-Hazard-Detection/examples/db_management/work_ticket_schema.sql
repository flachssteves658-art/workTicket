CREATE TABLE IF NOT EXISTS equipment_catalog (
    source_key VARCHAR(64) PRIMARY KEY,
    station_name VARCHAR(120) NOT NULL,
    equipment_name VARCHAR(255) NOT NULL,
    voltage_level VARCHAR(80),
    equipment_type VARCHAR(100),
    asset_no VARCHAR(120),
    running_no VARCHAR(255),
    interval_name VARCHAR(255),
    asset_status VARCHAR(40),
    running_status VARCHAR(40),
    dispatch_name VARCHAR(255),
    install_location VARCHAR(255),
    equipment_code VARCHAR(120),
    functional_location_code VARCHAR(120),
    normalized_search TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_equipment_station (station_name),
    INDEX idx_equipment_code (equipment_code),
    INDEX idx_equipment_function (functional_location_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cameras (
    camera_id VARCHAR(80) PRIMARY KEY,
    station_name VARCHAR(120) NOT NULL,
    nvr_name VARCHAR(80),
    channel_no VARCHAR(80),
    install_location VARCHAR(255),
    monitor_area VARCHAR(255),
    ip_address VARCHAR(45),
    running_status VARCHAR(40),
    retention_period VARCHAR(40),
    stream_config_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_camera_station (station_name),
    INDEX idx_camera_ip (ip_address),
    INDEX idx_camera_stream_config (stream_config_id),
    CONSTRAINT fk_camera_stream_config FOREIGN KEY (stream_config_id)
        REFERENCES stream_configs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS work_tickets (
    ticket_no VARCHAR(160) PRIMARY KEY,
    station_name VARCHAR(120),
    work_leader VARCHAR(120),
    planned_start_time VARCHAR(80),
    planned_end_time VARCHAR(80),
    actual_start_time VARCHAR(80),
    actual_end_time VARCHAR(80),
    status VARCHAR(40) NOT NULL DEFAULT 'recognized',
    source_file VARCHAR(500),
    structured_json LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_ticket_station (station_name),
    INDEX idx_ticket_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ticket_equipment (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_no VARCHAR(160) NOT NULL,
    equipment_source_key VARCHAR(64) NOT NULL,
    raw_equipment_name VARCHAR(255),
    standard_equipment_name VARCHAR(255) NOT NULL,
    equipment_code VARCHAR(120),
    interval_name VARCHAR(255),
    functional_location_code VARCHAR(120),
    match_confidence DECIMAL(5,4) NOT NULL,
    match_method VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ticket_equipment (ticket_no, equipment_source_key),
    CONSTRAINT fk_te_ticket FOREIGN KEY (ticket_no) REFERENCES work_tickets(ticket_no) ON DELETE CASCADE,
    CONSTRAINT fk_te_equipment FOREIGN KEY (equipment_source_key) REFERENCES equipment_catalog(source_key) ON DELETE CASCADE,
    INDEX idx_te_ticket (ticket_no),
    INDEX idx_te_equipment (equipment_source_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ticket_camera_binding (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_no VARCHAR(160) NOT NULL,
    equipment_source_key VARCHAR(64) NULL,
    camera_id VARCHAR(80) NOT NULL,
    match_score DECIMAL(5,4) NOT NULL,
    match_method TEXT,
    decision VARCHAR(40) NOT NULL,
    confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_by VARCHAR(120),
    monitor_start_time VARCHAR(80),
    monitor_end_time VARCHAR(80),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ticket_camera (ticket_no, camera_id),
    CONSTRAINT fk_tcb_ticket FOREIGN KEY (ticket_no) REFERENCES work_tickets(ticket_no) ON DELETE CASCADE,
    CONSTRAINT fk_tcb_equipment FOREIGN KEY (equipment_source_key) REFERENCES equipment_catalog(source_key) ON DELETE SET NULL,
    CONSTRAINT fk_tcb_camera FOREIGN KEY (camera_id) REFERENCES cameras(camera_id) ON DELETE CASCADE,
    INDEX idx_tcb_ticket (ticket_no),
    INDEX idx_tcb_camera (camera_id),
    INDEX idx_tcb_confirmed (confirmed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_detection_tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_key VARCHAR(220) NOT NULL,
    ticket_no VARCHAR(160) NOT NULL,
    monitor_start_time DATETIME NULL,
    monitor_end_time DATETIME NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'awaiting_stream_configuration',
    confirmed_by VARCHAR(120),
    status_message VARCHAR(500),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_detection_task_key (task_key),
    UNIQUE KEY uq_detection_task_ticket (ticket_no),
    CONSTRAINT fk_detection_task_ticket FOREIGN KEY (ticket_no)
        REFERENCES work_tickets(ticket_no) ON DELETE CASCADE,
    INDEX idx_detection_task_status (status),
    INDEX idx_detection_task_window (monitor_start_time, monitor_end_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_detection_task_streams (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id BIGINT NOT NULL,
    camera_id VARCHAR(80) NOT NULL,
    stream_config_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_detection_task_camera (task_id, camera_id),
    UNIQUE KEY uq_detection_task_stream (task_id, stream_config_id),
    CONSTRAINT fk_detection_task_stream_task FOREIGN KEY (task_id)
        REFERENCES ai_detection_tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_detection_task_stream_camera FOREIGN KEY (camera_id)
        REFERENCES cameras(camera_id) ON DELETE RESTRICT,
    CONSTRAINT fk_detection_task_stream_config FOREIGN KEY (stream_config_id)
        REFERENCES stream_configs(id) ON DELETE SET NULL,
    INDEX idx_detection_task_stream_camera (camera_id),
    INDEX idx_detection_task_stream_config (stream_config_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
