import subprocess
import json
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ..common.config import cfg, APP_PATH
from ..common.logger import get_logger

logger = get_logger('rclone')


@dataclass
class RCloneResult:
    success: bool
    stdout: str
    stderr: str
    return_code: int


def _resolve_path(value: str) -> str:
    if not value:
        return value
    p = Path(value)
    if p.is_absolute():
        return value
    return str(APP_PATH / value)


class RClone:

    def __init__(self, rclone_path: Optional[str] = None, config_path: Optional[str] = None):
        self.rclone_path = _resolve_path(rclone_path or cfg.rclonePath.value)
        self.config_path = _resolve_path(config_path or cfg.rcloneConfigPath.value) or None

    def _validate_remote_name(self, name: str) -> None:
        if not name:
            raise ValueError("远程存储名称不能为空")
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise ValueError(f"非法的远程存储名称: {name}")

    def _validate_option_key(self, key: str) -> None:
        if not key:
            raise ValueError("选项键名不能为空")
        if not re.match(r'^[a-zA-Z0-9_]+$', key):
            raise ValueError(f"非法的选项键名: {key}")

    def _sanitize_option_value(self, value: str) -> str:
        if value is None:
            return ""
        value = str(value)
        dangerous_chars = [';', '&', '|', '`', '$', '(', ')', '<', '>', '\\']
        for char in dangerous_chars:
            value = value.replace(char, '')
        return value

    def _build_command(self, *args, **kwargs) -> List[str]:
        cmd = [self.rclone_path]

        if self.config_path:
            cmd.extend(['--config', self.config_path])

        for arg in args:
            cmd.append(str(arg))

        for key, value in kwargs.items():
            if value is True:
                cmd.append(f'--{key.replace("_", "-")}')
            elif value is not False and value is not None:
                cmd.extend([f'--{key.replace("_", "-")}', str(value)])

        return cmd

    def _run(self, *args, **kwargs) -> RCloneResult:
        cmd = self._build_command(*args, **kwargs)

        safe_cmd = []
        for c in cmd:
            if '=' in c and any(s in c.lower() for s in ['pass', 'secret', 'token', 'key']):
                key_part = c.split('=', 1)[0]
                safe_cmd.append(f'{key_part}=***')
            else:
                safe_cmd.append(c)
        logger.info(f'[RClone] 执行命令: {" ".join(safe_cmd)}')

        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            result = RCloneResult(
                success=process.returncode == 0,
                stdout=process.stdout,
                stderr=process.stderr,
                return_code=process.returncode
            )
            if result.success:
                logger.info(f'[RClone] 命令成功 (return_code=0), stdout长度={len(result.stdout)}')
            else:
                logger.error(f'[RClone] 命令失败: return_code={result.return_code}, '
                           f'stderr={result.stderr[:300] if result.stderr else "N/A"}')
            return result
        except subprocess.TimeoutExpired:
            logger.error('[RClone] 命令执行超时（300秒）')
            return RCloneResult(
                success=False,
                stdout='',
                stderr='命令执行超时（300秒）',
                return_code=-1
            )
        except subprocess.SubprocessError as e:
            logger.error(f'[RClone] 子进程错误: {e}')
            return RCloneResult(
                success=False,
                stdout='',
                stderr=f'子进程错误: {e}',
                return_code=-1
            )
        except OSError as e:
            logger.error(f'[RClone] 系统错误: {e}')
            return RCloneResult(
                success=False,
                stdout='',
                stderr=f'系统错误: {e}',
                return_code=-1
            )

    def _run_json(self, *args, **kwargs) -> Tuple[bool, Any]:
        result = self._run(*args, **kwargs)
        if result.success and result.stdout.strip():
            try:
                return True, json.loads(result.stdout)
            except json.JSONDecodeError:
                return False, result.stderr or "无效的 JSON 响应"
        return result.success, result.stderr if not result.success else []

    def version(self) -> str:
        result = self._run('version')
        if result.success:
            return result.stdout.split('\n')[0]
        return "未知"

    def listremotes(self) -> List[str]:
        result = self._run('listremotes')
        if result.success:
            remotes = [r.rstrip(':') for r in result.stdout.strip().split('\n') if r]
            return remotes
        return []

    def config_dump(self) -> Dict[str, Dict[str, str]]:
        success, data = self._run_json('config', 'dump')
        return data if success and isinstance(data, dict) else {}

    def config_get(self, remote: str) -> Dict[str, str]:
        all_config = self.config_dump()
        return all_config.get(remote, {})

    def config_create(self, name: str, remote_type: str, **options) -> RCloneResult:
        logger.info(f'[RClone] config_create: name={name}, type={remote_type}, options_count={len(options)}')
        self._validate_remote_name(name)
        self._validate_remote_name(remote_type)

        args = ['config', 'create', name, remote_type]
        for key, value in options.items():
            self._validate_option_key(key)
            sanitized_value = self._sanitize_option_value(value)
            args.extend([f'{key}={sanitized_value}'])
        return self._run(*args)

    def config_update(self, name: str, **options) -> RCloneResult:
        logger.info(f'[RClone] config_update: name={name}, options_count={len(options)}')
        self._validate_remote_name(name)

        args = ['config', 'update', name]
        for key, value in options.items():
            self._validate_option_key(key)
            sanitized_value = self._sanitize_option_value(value)
            args.extend([f'{key}={sanitized_value}'])
        return self._run(*args)

    def config_delete(self, name: str) -> RCloneResult:
        logger.info(f'[RClone] config_delete: name={name}')
        self._validate_remote_name(name)
        return self._run('config', 'delete', name)

    def lsjson(self, remote_path: str, recursive: bool = False) -> Tuple[bool, List[Dict]]:
        args = ['lsjson', remote_path]
        if recursive:
            args.append('--recursive')
        return self._run_json(*args)

    def ls(self, remote_path: str) -> List[Dict[str, Any]]:
        success, data = self.lsjson(remote_path)
        return data if success else []

    def mkdir(self, remote_path: str) -> RCloneResult:
        return self._run('mkdir', remote_path)

    def rmdir(self, remote_path: str) -> RCloneResult:
        return self._run('rmdir', remote_path)

    def purge(self, remote_path: str) -> RCloneResult:
        return self._run('purge', remote_path)

    def delete_file(self, remote_path: str) -> RCloneResult:
        return self._run('deletefile', remote_path)

    def copy(self, source: str, dest: str, **options) -> RCloneResult:
        return self._run('copy', source, dest, **options)

    def move(self, source: str, dest: str, **options) -> RCloneResult:
        return self._run('move', source, dest, **options)

    def sync(self, source: str, dest: str, **options) -> RCloneResult:
        return self._run('sync', source, dest, **options)

    def check(self, remote: str) -> RCloneResult:
        return self._run('lsd', f'{remote}:', max_depth=1)

    def about(self, remote: str) -> Tuple[bool, Dict]:
        return self._run_json('about', f'{remote}:', json=True)

    def size(self, remote_path: str) -> Tuple[bool, Dict]:
        return self._run_json('size', remote_path, json=True)
