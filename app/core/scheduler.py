import json
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, Optional, Set
from PySide6.QtCore import QObject, Signal, QTimer
import logging

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False


logger = logging.getLogger(__name__)


class SchedulerThread(QObject):
    tick = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.setInterval(60000)
        self._last_minute = -1

    def _on_tick(self):
        now = datetime.now()
        current_minute = now.minute

        if current_minute != self._last_minute:
            self._last_minute = current_minute
            self.tick.emit()

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
            self._last_minute = datetime.now().minute
            self.tick.emit()

    def stop(self):
        self._timer.stop()


class SyncScheduler(QObject):

    taskDue = Signal(str)

    def __init__(self, parent=None, state_file: Optional[Path] = None):
        super().__init__(parent)
        self._scheduled_tasks: Dict[str, str] = {}
        self._last_run_times: Dict[str, datetime] = {}
        self._triggered_tasks: Set[str] = set()
        self._scheduler_thread: Optional[SchedulerThread] = None
        self._check_callback: Optional[Callable[[str], None]] = None
        self._lock = Lock()
        self._state_file = state_file
        self._last_check_time: Optional[datetime] = None

        if not CRONITER_AVAILABLE:
            logger.warning("croniter 模块未安装，Cron 表达式功能将不可用。使用: pip install croniter")

    def set_check_callback(self, callback: Callable[[str], None]):
        self._check_callback = callback

    def start(self):
        if self._scheduler_thread is None:
            self._scheduler_thread = SchedulerThread(self)
            self._scheduler_thread.tick.connect(self._on_tick)
        if not self._scheduler_thread._timer.isActive():
            self._scheduler_thread.start()
            logger.info("调度器已启动")

    def stop(self):
        if self._scheduler_thread:
            self._scheduler_thread.stop()
            logger.info("调度器已停止")

    def add_task(self, task_id: str, cron_expression: str, last_run: Optional[datetime] = None):
        if not CRONITER_AVAILABLE:
            logger.error(f"无法添加定时任务 {task_id}: croniter 模块未安装")
            return False

        try:
            croniter(cron_expression)
            with self._lock:
                self._scheduled_tasks[task_id] = cron_expression
                if last_run:
                    self._last_run_times[task_id] = last_run
            logger.info(f"已添加定时任务 {task_id}: {cron_expression}")
            return True
        except (ValueError, KeyError) as e:
            logger.error(f"无效的 Cron 表达式 '{cron_expression}': {e}")
            return False

    def remove_task(self, task_id: str):
        with self._lock:
            if task_id in self._scheduled_tasks:
                del self._scheduled_tasks[task_id]
            if task_id in self._last_run_times:
                del self._last_run_times[task_id]
            if task_id in self._triggered_tasks:
                self._triggered_tasks.discard(task_id)
        logger.info(f"已移除定时任务 {task_id}")

    def update_task(self, task_id: str, cron_expression: str):
        with self._lock:
            last_run = self._last_run_times.get(task_id)
        if task_id in self._scheduled_tasks:
            return self.add_task(task_id, cron_expression, last_run)
        return False

    def update_last_run(self, task_id: str, run_time: Optional[datetime] = None):
        with self._lock:
            if task_id in self._scheduled_tasks:
                self._last_run_times[task_id] = run_time or datetime.now()
                self._triggered_tasks.discard(task_id)

    def get_next_run(self, task_id: str) -> Optional[datetime]:
        if not CRONITER_AVAILABLE:
            return None

        with self._lock:
            cron_expression = self._scheduled_tasks.get(task_id)
            base_time = self._last_run_times.get(task_id, datetime.now())

        if not cron_expression:
            return None

        try:
            itr = croniter(cron_expression, base_time)
            return itr.get_next(datetime)
        except (ValueError, TypeError) as e:
            logger.error(f"无效的 Cron 表达式，无法计算下次运行时间: {e}")
            return None
        except Exception as e:
            logger.error(f"计算下次运行时间失败: {e}")
            return None

    def get_next_run_text(self, task_id: str) -> str:
        next_run = self.get_next_run(task_id)
        if next_run:
            return next_run.strftime("%Y-%m-%d %H:%M")
        return "未设置"

    def is_scheduled(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._scheduled_tasks

    def _on_tick(self):
        if not CRONITER_AVAILABLE:
            return

        now = datetime.now()

        with self._lock:
            if self._last_check_time and now < self._last_check_time:
                logger.warning("检测到系统时间回拨，重置调度状态")
                self._triggered_tasks.clear()
            self._last_check_time = now

            tasks_copy = dict(self._scheduled_tasks)
            triggered_copy = set(self._triggered_tasks)

        for task_id, cron_expression in tasks_copy.items():
            try:
                with self._lock:
                    last_run = self._last_run_times.get(task_id)

                base_time = last_run or datetime.fromtimestamp(0)
                itr = croniter(cron_expression, base_time)
                next_run = itr.get_next(datetime)

                if now >= next_run:
                    with self._lock:
                        if task_id in self._triggered_tasks:
                            continue
                        self._triggered_tasks.add(task_id)

                    logger.info(f"任务 {task_id} 已到期，下次运行时间: {next_run}")
                    with self._lock:
                        self._last_run_times[task_id] = now
                    self.taskDue.emit(task_id)

                    if self._check_callback:
                        try:
                            self._check_callback(task_id)
                        except Exception as e:
                            logger.error(f"回调函数执行出错: {e}")

            except (ValueError, KeyError) as e:
                logger.error(f"无效的 Cron 表达式，任务 {task_id}: {e}")
            except TypeError as e:
                logger.error(f"类型错误，任务 {task_id}: {e}")
            except Exception as e:
                logger.error(f"检查任务 {task_id} 时发生未知错误: {e}", exc_info=True)

    def validate_cron(self, expression: str) -> bool:
        if not CRONITER_AVAILABLE:
            return False
        if not expression or not isinstance(expression, str):
            return False
        try:
            croniter(expression)
            return True
        except (ValueError, KeyError, TypeError) as e:
            logger.debug(f"无效的 Cron 表达式 '{expression}': {e}")
            return False
        except Exception as e:
            logger.error(f"验证 Cron 表达式时发生未知错误: {e}")
            return False

    def get_cron_description(self, expression: str) -> str:
        descriptions = {
            "0 0 * * *": "每天午夜",
            "0 2 * * *": "每天凌晨 2 点",
            "0 8 * * *": "每天早上 8 点",
            "0 12 * * *": "每天中午 12 点",
            "0 18 * * *": "每天晚上 6 点",
            "0 */6 * * *": "每 6 小时",
            "0 */12 * * *": "每 12 小时",
            "0 0 * * 0": "每周日午夜",
            "0 0 1 * *": "每月 1 号",
            "0 0 1 1 *": "每年 1 月 1 日",
            "*/5 * * * *": "每 5 分钟",
            "*/15 * * * *": "每 15 分钟",
            "*/30 * * * *": "每 30 分钟",
        }

        return descriptions.get(expression.strip(), expression)

    def clear(self):
        with self._lock:
            self._scheduled_tasks.clear()
            self._last_run_times.clear()
            self._triggered_tasks.clear()
            self._last_check_time = None

    def get_all_scheduled_tasks(self) -> Dict[str, str]:
        with self._lock:
            return self._scheduled_tasks.copy()
