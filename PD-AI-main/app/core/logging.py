import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def _get_log_dir() -> Path:
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _get_log_level() -> int:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def _get_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def setup_logging() -> None:
    log_dir = _get_log_dir()
    level = _get_log_level()

    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(level)

    formatter = _get_formatter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    app_file = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_file.setLevel(level)
    app_file.setFormatter(formatter)

    error_file = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(formatter)

    root.addHandler(console_handler)
    root.addHandler(app_file)
    root.addHandler(error_file)


def _ensure_module_handler(logger: logging.Logger, name: str) -> None:
    log_dir = _get_log_dir()
    level = _get_log_level()
    formatter = _get_formatter()

    safe_name = name.replace("/", "_").replace("\\", "_").replace(".", "_")
    module_log_path = log_dir / f"{safe_name}.log"

    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(module_log_path):
            return

    module_file = RotatingFileHandler(
        module_log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    module_file.setLevel(level)
    module_file.setFormatter(formatter)
    logger.addHandler(module_file)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    logger_name = name or "app"
    logger = logging.getLogger(logger_name)
    _ensure_module_handler(logger, logger_name)
    return logger
