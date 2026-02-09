import os
import re
from dataclasses import dataclass, field
from typing import Optional, Literal
from enum import Enum


class MountStatus(Enum):
    UNMOUNTED = "unmounted"
    MOUNTING = "mounting"
    MOUNTED = "mounted"
    ERROR = "error"


CacheMode = Literal["off", "minimal", "writes", "full"]
MountSource = Literal["config", "discovered"]


@dataclass
class Mount:

    remote_name: str
    remote_path: str
    drive_letter: str
    status: MountStatus = MountStatus.UNMOUNTED
    auto_mount: bool = False
    read_only: bool = False
    cache_mode: CacheMode = "off"
    vfs_cache_max_size: str = "10G"
    process_id: Optional[int] = None
    error_message: Optional[str] = None
    source: MountSource = "config"

    def __post_init__(self):
        if not self.drive_letter or not re.match(r'^[A-Za-z]$', self.drive_letter):
            raise ValueError(f"Invalid drive letter: {self.drive_letter}. Must be a single letter A-Z.")
        self.drive_letter = self.drive_letter.upper()

        if not self.remote_name or '..' in self.remote_name or '/' in self.remote_name or '\\' in self.remote_name:
            raise ValueError(f"Invalid remote name: {self.remote_name}")

        valid_cache_modes = ("off", "minimal", "writes", "full")
        if self.cache_mode not in valid_cache_modes:
            raise ValueError(f"Invalid cache_mode: {self.cache_mode}. Must be one of {valid_cache_modes}")

        if not re.match(r'^\d+[KMGT]?$', self.vfs_cache_max_size, re.IGNORECASE):
            raise ValueError(f"Invalid vfs_cache_max_size: {self.vfs_cache_max_size}")

    @property
    def remote_full_path(self) -> str:
        path = self.remote_path.strip('/')
        return f"{self.remote_name}:{path}" if path else f"{self.remote_name}:"

    @property
    def is_mounted(self) -> bool:
        if os.name == 'nt':
            return self.check_drive_exists()
        return self.status == MountStatus.MOUNTED

    def check_drive_exists(self) -> bool:
        if os.name != 'nt':
            return False
        try:
            return os.path.exists(f"{self.drive_letter}:\\")
        except Exception:
            return False

    def refresh_status(self) -> bool:
        is_mounted = self.check_drive_exists()

        if is_mounted and self.status != MountStatus.MOUNTED:
            self.status = MountStatus.MOUNTED
        elif not is_mounted and self.status == MountStatus.MOUNTED:
            self.status = MountStatus.UNMOUNTED
            self.process_id = None

        return is_mounted

    def to_dict(self) -> dict:
        if self.source == "discovered":
            return None
        return {
            'remote_name': self.remote_name,
            'remote_path': self.remote_path,
            'drive_letter': self.drive_letter,
            'status': self.status.value,
            'auto_mount': self.auto_mount,
            'read_only': self.read_only,
            'cache_mode': self.cache_mode,
            'vfs_cache_max_size': self.vfs_cache_max_size,
            'process_id': self.process_id,
            'error_message': self.error_message,
            'source': self.source
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Mount':
        if 'remote_name' not in data:
            raise KeyError("Missing required field: 'remote_name'")
        if 'drive_letter' not in data:
            raise KeyError("Missing required field: 'drive_letter'")

        status_value = data.get('status', 'unmounted')
        try:
            status = MountStatus(status_value)
        except ValueError:
            status = MountStatus.UNMOUNTED

        mount = cls(
            remote_name=data['remote_name'],
            remote_path=data.get('remote_path', ''),
            drive_letter=data['drive_letter'],
            status=status,
            auto_mount=data.get('auto_mount', False),
            read_only=data.get('read_only', False),
            cache_mode=data.get('cache_mode', 'off'),
            vfs_cache_max_size=data.get('vfs_cache_max_size', '10G'),
            source=data.get('source', 'config')
        )

        mount.process_id = data.get('process_id')
        mount.error_message = data.get('error_message')

        return mount

    @classmethod
    def from_process_info(cls, drive_letter: str, process_id: int,
                          remote_name: str = "") -> 'Mount':
        """从进程信息创建发现挂载。"""
        if not remote_name:
            remote_name = f"unknown_{drive_letter}"
        mount = cls(
            remote_name=remote_name,
            remote_path="",
            drive_letter=drive_letter,
            status=MountStatus.MOUNTED,
            source="discovered",
        )
        mount.process_id = process_id
        return mount

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mount):
            return NotImplemented
        return self.remote_name == other.remote_name and self.drive_letter == other.drive_letter

    def __hash__(self) -> int:
        return hash((self.remote_name, self.drive_letter))
