from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class SyncMode(Enum):
    SYNC = "sync"
    COPY = "copy"
    MOVE = "move"
    BISYNC = "bisync"


class SyncStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class SyncTask:

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source: str = ""
    destination: str = ""
    mode: SyncMode = SyncMode.SYNC
    status: SyncStatus = SyncStatus.IDLE
    _progress: int = 0

    delete_excluded: bool = False
    dry_run: bool = False
    bandwidth_limit: str = ""
    exclude_patterns: List[str] = field(default_factory=list)

    scheduled: bool = False
    cron_expression: str = ""

    last_run: Optional[datetime] = None
    files_transferred: int = 0
    bytes_transferred: int = 0
    error_message: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.exclude_patterns, list):
            object.__setattr__(self, 'exclude_patterns', [])

        if not self.id or not isinstance(self.id, str):
            object.__setattr__(self, 'id', str(uuid.uuid4())[:8])

        if not (0 <= self._progress <= 100):
            object.__setattr__(self, '_progress', max(0, min(100, self._progress)))

    @property
    def progress(self) -> int:
        return self._progress

    @progress.setter
    def progress(self, value: int):
        if not isinstance(value, (int, float)):
            raise TypeError("进度必须是数字")
        value = int(value)
        if not (0 <= value <= 100):
            raise ValueError(f"进度必须在 0-100 之间，当前值: {value}")
        self._progress = value

    def to_dict(self) -> dict:
        result = {
            'id': self.id,
            'name': self.name,
            'source': self.source,
            'destination': self.destination,
            'mode': self.mode.value,
            'status': self.status.value,
            'progress': self.progress,
            'delete_excluded': self.delete_excluded,
            'dry_run': self.dry_run,
            'bandwidth_limit': self.bandwidth_limit,
            'exclude_patterns': list(self.exclude_patterns),
            'scheduled': self.scheduled,
            'cron_expression': self.cron_expression
        }

        if self.last_run:
            result['last_run'] = self.last_run.isoformat()
        if self.files_transferred is not None:
            result['files_transferred'] = self.files_transferred
        if self.bytes_transferred is not None:
            result['bytes_transferred'] = self.bytes_transferred
        if self.error_message is not None:
            result['error_message'] = self.error_message

        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'SyncTask':
        try:
            mode = SyncMode(data.get('mode', 'sync'))
        except ValueError as e:
            raise ValueError(f"Invalid sync mode: {data.get('mode')}") from e

        try:
            status = SyncStatus(data.get('status', 'idle'))
        except ValueError as e:
            raise ValueError(f"Invalid sync status: {data.get('status')}") from e

        task = cls(
            id=data.get('id', str(uuid.uuid4())[:8]),
            name=data.get('name', ''),
            source=data.get('source', ''),
            destination=data.get('destination', ''),
            mode=mode,
            status=status,
            delete_excluded=data.get('delete_excluded', False),
            dry_run=data.get('dry_run', False),
            bandwidth_limit=data.get('bandwidth_limit', ''),
            exclude_patterns=list(data.get('exclude_patterns', [])),
            scheduled=data.get('scheduled', False),
            cron_expression=data.get('cron_expression', '')
        )

        if 'progress' in data:
            task.progress = data['progress']

        if 'last_run' in data and data['last_run']:
            try:
                task.last_run = datetime.fromisoformat(data['last_run'])
            except (ValueError, TypeError) as e:
                logger.warning(f"无法解析 last_run 日期: {data['last_run']}, 错误: {e}")
        if 'files_transferred' in data:
            task.files_transferred = data['files_transferred']
        if 'bytes_transferred' in data:
            task.bytes_transferred = data['bytes_transferred']
        if 'error_message' in data:
            task.error_message = data['error_message']

        return task

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SyncTask):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
