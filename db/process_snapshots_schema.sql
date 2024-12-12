CREATE TABLE process_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    snapshot_datetime DATETIME,
    host VARCHAR(255),
    username VARCHAR(255),
    comm VARCHAR(255),
    total_cpu_norm FLOAT,
    total_rss FLOAT,
    total_vsz FLOAT,
    process_count INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_snapshot_datetime (snapshot_datetime),
    INDEX idx_host (host),
    INDEX idx_composite (snapshot_datetime, host, username)
);