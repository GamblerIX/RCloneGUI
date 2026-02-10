import logging
import logging.handlers
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import APP_PATH


class AppLogger:

    _instance: Optional['AppLogger'] = None
    _initialized = False
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        with self._lock:
            if AppLogger._initialized:
                return

            self._logger = logging.getLogger('RCloneGUI')
            self._logger.setLevel(logging.DEBUG)

            self._log_dir = APP_PATH / 'logs'
            self._log_dir.mkdir(parents=True, exist_ok=True)

            self._setup_handlers()

            AppLogger._initialized = True

    def _setup_handlers(self):
        self._logger.handlers.clear()

        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        file_handler = logging.handlers.RotatingFileHandler(
            self._log_dir / 'app.log',
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)

        error_handler = logging.handlers.RotatingFileHandler(
            self._log_dir / 'error.log',
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self._logger.addHandler(error_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def debug(self, msg: str, **kwargs):
        self._logger.debug(msg, **kwargs)

    def info(self, msg: str, **kwargs):
        self._logger.info(msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        self._logger.warning(msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self._logger.error(msg, **kwargs)

    def critical(self, msg: str, **kwargs):
        self._logger.critical(msg, **kwargs)

    def get_log_dir(self) -> Path:
        return self._log_dir

    def get_log_files(self) -> list:
        if self._log_dir.exists():
            return sorted(self._log_dir.glob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
        return []

    def clear_old_logs(self, days: int = 30):
        cutoff = datetime.now() - timedelta(days=days)
        log_files = self._log_dir.glob('*.log*')

        for log_file in log_files:
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink()
                    self._logger.info(f'已清理旧日志文件: {log_file.name}')
            except Exception as e:
                self._logger.error(f'清理日志文件失败 {log_file}: {e}')

    def read_log_content(self, filename: str, lines: int = 100) -> str:
        log_file = self._log_dir / filename
        if not log_file.exists():
            return f"日志文件不存在: {filename}"

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except Exception as e:
            return f"读取日志失败: {e}"


app_logger = AppLogger()


def get_logger(name: str = None) -> logging.Logger:
    if name:
        return logging.getLogger(f'RCloneGUI.{name}')
    return app_logger.logger
