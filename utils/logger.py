"""统一日志：控制台 + 按日切割的文件日志"""

import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
from pathlib import Path


def setup_logger(name: str = "infoCollector", log_dir: str = "logs") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    configured_level = os.environ.get("INFOCOLLECTOR_LOG_LEVEL", "INFO").upper()
    console_level = getattr(logging, configured_level, logging.INFO)
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 文件（按日期）
    log_dir = os.environ.get("INFOCOLLECTOR_LOG_DIR", log_dir)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    process_name = os.environ.get("INFOCOLLECTOR_PROCESS_NAME", "").strip()
    if not process_name and len(sys.argv) > 1:
        process_name = Path(sys.argv[1]).stem
    safe_process = "".join(char for char in process_name if char.isalnum() or char in "-_") or "app"
    file_handler = TimedRotatingFileHandler(
        Path(log_dir) / f"infocollector-{safe_process}.log",
        when="midnight",
        interval=1,
        backupCount=max(1, int(os.environ.get("INFOCOLLECTOR_LOG_RETENTION_DAYS", "14"))),
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
