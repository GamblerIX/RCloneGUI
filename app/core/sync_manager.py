import json
import os
import re
import subprocess
from datetime import datetime
from threading import Lock
from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal, QThread, QTimer

from .rclone import RClone
from .scheduler import SyncScheduler
from ..common.config import APP_PATH
from ..common.logger import get_logger
from ..common.signal_bus import signalBus
from ..models.sync_task import SyncMode, SyncStatus, SyncTask

logger = get_logger('sync_manager')


class SyncWorker(QThread):
    started = Signal(str)
    progress = Signal(str, int, int, int)
    stats_update = Signal(str, dict)
    finished = Signal(str, bool, str)

    _PROGRESS_RE = re.compile(
        r'(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB|TiB|B)\s*/\s*(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB|TiB|B).*?(\d+)%'
    )
    _FILES_RE = re.compile(r'Transferred:\s*(\d+)/(\d+)')
    _SPEED_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB)/s')
    _ETA_RE = re.compile(r'ETA\s*(\S+)')

    def __init__(self, rclone: RClone, task: SyncTask):
        super().__init__()
        self.rclone = rclone
        self.task = task
        self._cancelled = False
        self._process = None

    def run(self):
        self.started.emit(self.task.id)

        cmd = [self.rclone.rclone_path]

        if self.rclone.config_path:
            cmd.extend(['--config', self.rclone.config_path])

        cmd.extend([
            '--progress',
            '--stats-one-line',
            '--stats=1s',
        ])

        if self.task.bandwidth_limit:
            cmd.extend(['--bwlimit', self.task.bandwidth_limit])
        if self.task.dry_run:
            cmd.append('--dry-run')
        if self.task.delete_excluded:
            cmd.append('--delete-excluded')

        for pattern in self.task.exclude_patterns:
            cmd.extend(['--exclude', pattern])

        if self.task.mode == SyncMode.SYNC:
            cmd.extend(['sync', self.task.source, self.task.destination])
        elif self.task.mode == SyncMode.COPY:
            cmd.extend(['copy', self.task.source, self.task.destination])
        elif self.task.mode == SyncMode.MOVE:
            cmd.extend(['move', self.task.source, self.task.destination])
        else:
            cmd.extend(['bisync', self.task.source, self.task.destination])

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            while True:
                if self._cancelled:
                    self._process.terminate()
                    break

                line = self._process.stderr.readline()
                if not line:
                    break

                self._parse_progress(line.strip())

            return_code = self._process.wait()
            success = return_code == 0

            if self._cancelled:
                message = "已取消"
            elif success:
                message = "完成"
            else:
                message = f"失败 (返回码: {return_code})"

            self.finished.emit(self.task.id, success and not self._cancelled, message)

        except Exception as e:
            self.finished.emit(self.task.id, False, str(e))

    def _parse_progress(self, line: str):

        if not line:
            return

        stats = {}
        matched = False

        progress_match = self._PROGRESS_RE.search(line)
        if progress_match:
            matched = True
            transferred = float(progress_match.group(1))
            transferred_unit = progress_match.group(2)
            total = float(progress_match.group(3))
            total_unit = progress_match.group(4)
            percentage = int(progress_match.group(5))

            units = {'B': 1, 'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3, 'TiB': 1024**4}
            bytes_transferred = int(transferred * units.get(transferred_unit, 1))
            bytes_total = int(total * units.get(total_unit, 1))

            stats['percentage'] = percentage
            stats['bytes_transferred'] = bytes_transferred
            stats['bytes_total'] = bytes_total

            self.progress.emit(self.task.id, percentage, 0, bytes_transferred)
        else:
            logger.debug(f"进度正则不匹配: {line[:100]}")

        files_match = self._FILES_RE.search(line)
        if files_match:
            matched = True
            files_done = int(files_match.group(1))
            files_total = int(files_match.group(2))
            stats['files_transferred'] = files_done
            stats['files_total'] = files_total

        speed_match = self._SPEED_RE.search(line)
        if speed_match:
            matched = True
            speed = float(speed_match.group(1))
            unit = speed_match.group(2)
            units = {'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3}
            stats['speed'] = int(speed * units.get(unit, 1))

        eta_match = self._ETA_RE.search(line)
        if eta_match:
            matched = True
            stats['eta'] = eta_match.group(1)

        if stats:
            self.stats_update.emit(self.task.id, stats)
        elif not matched:
            logger.debug(f"未匹配的输出: {line[:100]}")

    def cancel(self):
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=2)
                self._process.communicate()
            except (ProcessLookupError, PermissionError) as e:
                logger.debug(f"Failed to terminate process: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error terminating process: {e}")
            finally:
                self._process = None


class SyncManager(QObject):

    taskStatusChanged = Signal(str, SyncStatus)
    taskProgress = Signal(str, int, int, int)
    taskStatsUpdate = Signal(str, dict)
    taskError = Signal(str, str)
    taskCompleted = Signal(str, bool, str)

    def __init__(self, rclone: Optional[RClone] = None):
        super().__init__()
        self.rclone = rclone or RClone()
        self.tasks: Dict[str, SyncTask] = {}
        self.workers: Dict[str, SyncWorker] = {}
        self._config_file = APP_PATH / "config" / "sync_tasks.json"
        self._lock = Lock()

        self.scheduler = SyncScheduler(self)
        self.scheduler.taskDue.connect(self._on_scheduled_task_due)
        self.scheduler.start()

        self.load_tasks()

    def save_tasks(self):
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._lock:
                data = [t.to_dict() for t in self.tasks.values()]
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f'已保存 {len(data)} 个同步任务')
        except Exception as e:
            logger.error(f'保存同步任务失败: {e}')

    def add_task(self, name: str, source: str, destination: str,
                 mode: SyncMode = SyncMode.SYNC, **options) -> SyncTask:
        task = SyncTask(
            name=name,
            source=source,
            destination=destination,
            mode=mode,
            **options
        )
        with self._lock:
            self.tasks[task.id] = task
        self.save_tasks()
        logger.info(f'添加同步任务: {name} ({mode.value})')
        return task

    def remove_task(self, task_id: str):
        with self._lock:
            task = self.tasks.get(task_id)
        if task:
            task_name = task.name
            with self._lock:
                worker = self.workers.pop(task_id, None)
            if worker:
                worker.cancel()
            with self._lock:
                del self.tasks[task_id]
            self.scheduler.remove_task(task_id)
            self.save_tasks()
            logger.info(f'删除同步任务: {task_name}')

    def run_task(self, task_id: str) -> bool:
        with self._lock:
            task = self.tasks.get(task_id)
        if not task:
            logger.warning(f'运行任务失败: 任务 {task_id} 不存在')
            return False

        if task.status == SyncStatus.RUNNING:
            logger.debug(f'任务 {task.name} 已在运行中')
            return False

        logger.info(f'开始同步任务: {task.name} ({task.mode.value})')
        task.status = SyncStatus.RUNNING
        self.taskStatusChanged.emit(task_id, SyncStatus.RUNNING)

        worker = SyncWorker(self.rclone, task)
        worker.started.connect(self._on_task_started)
        worker.progress.connect(self._on_task_progress)
        worker.stats_update.connect(self._on_task_stats_update)
        worker.finished.connect(self._on_task_finished)
        with self._lock:
            self.workers[task_id] = worker
        worker.start()

        return True

    def cancel_task(self, task_id: str):
        with self._lock:
            worker = self.workers.pop(task_id, None)
        if worker:
            worker.cancel()

        with self._lock:
            task = self.tasks.get(task_id)
        if task:
            task.status = SyncStatus.IDLE
            self.taskStatusChanged.emit(task_id, SyncStatus.IDLE)

    def _on_task_started(self, task_id: str):
        if task_id in self.tasks:
            self.tasks[task_id].status = SyncStatus.RUNNING
            self.taskStatusChanged.emit(task_id, SyncStatus.RUNNING)

    def _on_task_progress(self, task_id: str, percentage: int, files: int, bytes_transferred: int):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.progress = percentage
            task.files_transferred = files
            task.bytes_transferred = bytes_transferred
            self.taskProgress.emit(task_id, percentage, files, bytes_transferred)

    def _on_task_stats_update(self, task_id: str, stats: dict):
        self.taskStatsUpdate.emit(task_id, stats)

    def _on_task_finished(self, task_id: str, success: bool, message: str):
        try:
            with self._lock:
                task = self.tasks.get(task_id)

            if task:
                task.last_run = datetime.now()

                if success:
                    task.status = SyncStatus.COMPLETED
                    task.error_message = None
                    logger.info(f'同步任务完成: {task.name} - {message}')
                else:
                    task.status = SyncStatus.ERROR
                    task.error_message = message
                    self.taskError.emit(task_id, message)
                    logger.error(f'同步任务失败: {task.name} - {message}')

                self.taskStatusChanged.emit(task_id, task.status)
                self.taskCompleted.emit(task_id, success, message)
                self.save_tasks()

                if task.scheduled:
                    self.scheduler.update_last_run(task_id, task.last_run)

            with self._lock:
                self.workers.pop(task_id, None)
        except Exception as e:
            logger.error(f'处理任务完成信号时出错: {e}')

    def _on_scheduled_task_due(self, task_id: str):
        try:
            with self._lock:
                task = self.tasks.get(task_id)
            if task:
                signalBus.scheduledTaskDue.emit(task_id, task.name)
                self.run_task(task_id)
        except Exception as e:
            logger.error(f'处理定时任务到期时出错: {e}')

    def enable_schedule(self, task_id: str, cron_expression: str) -> bool:
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]
        task.scheduled = True
        task.cron_expression = cron_expression

        success = self.scheduler.add_task(task_id, cron_expression, task.last_run)
        if success:
            self.save_tasks()
            return True
        else:
            task.scheduled = False
            return False

    def disable_schedule(self, task_id: str):
        with self._lock:
            task = self.tasks.get(task_id)
        if task:
            task.scheduled = False
            task.cron_expression = ""
            self.scheduler.remove_task(task_id)
            self.save_tasks()

    def update_schedule(self, task_id: str, cron_expression: str) -> bool:
        with self._lock:
            task = self.tasks.get(task_id)
        if not task:
            return False

        task.cron_expression = cron_expression

        if task.scheduled:
            return self.scheduler.update_task(task_id, cron_expression)
        return True

    def get_next_run_time(self, task_id: str) -> Optional[str]:
        with self._lock:
            task = self.tasks.get(task_id)
        if task and task.scheduled:
            return self.scheduler.get_next_run_text(task_id)
        return None

    def validate_cron(self, expression: str) -> bool:
        return self.scheduler.validate_cron(expression)

    def shutdown(self):
        with self._lock:
            task_ids = list(self.workers.keys())
        for task_id in task_ids:
            self.cancel_task(task_id)

        self.scheduler.stop()

    def _initialize_schedules(self):
        scheduled_count = 0
        with self._lock:
            tasks_copy = list(self.tasks.values())
        for task in tasks_copy:
            if task.scheduled and task.cron_expression:
                self.scheduler.add_task(task.id, task.cron_expression, task.last_run)
                scheduled_count += 1
        if scheduled_count > 0:
            logger.info(f'已初始化 {scheduled_count} 个定时任务')

    def load_tasks(self) -> bool:
        if not self._config_file.exists():
            logger.info(f'同步任务文件不存在: {self._config_file}')
            return False

        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            with self._lock:
                self.tasks.clear()
                for task_data in data:
                    try:
                        task = SyncTask.from_dict(task_data)
                        self.tasks[task.id] = task
                    except (KeyError, ValueError) as e:
                        logger.warning(f'跳过无效的任务数据: {e}')

            logger.info(f'已加载 {len(self.tasks)} 个同步任务')
            self._initialize_schedules()
            return True
        except json.JSONDecodeError as e:
            logger.error(f'加载同步任务失败（JSON解析错误）: {e}')
            return False
        except Exception as e:
            logger.error(f'加载同步任务失败: {e}', exc_info=True)
            return False
