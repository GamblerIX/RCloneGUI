import json
import os
import re
import signal
import string
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Set

from PySide6.QtCore import QObject, Signal, QThread

from ..common.config import APP_PATH, cfg, get_cache_dir
from ..common.logger import get_logger
from ..models.mount import Mount, MountStatus
from .rclone import RClone

logger = get_logger('mount_manager')


def _parse_rclone_mount_cmdline(cmdline: str) -> tuple | None:
    """从 rclone mount 命令行中提取盘符和远程存储名称。

    支持的命令行格式示例：
    - rclone mount remote: X: --options...
    - rclone mount remote:path X: --options...
    - rclone mount remote:path/subdir X:
    - "C:\\path\\to\\rclone.exe" mount myremote:folder Z: --vfs-cache-mode full

    Args:
        cmdline: rclone mount 命令行字符串。

    Returns:
        (drive_letter, remote_name) 元组，解析失败时返回 None。
        drive_letter 为大写字母 A-Z，remote_name 为冒号前的远程存储名称。
    """
    if not cmdline or not isinstance(cmdline, str):
        logger.debug(f'命令行解析跳过: 输入为空或非字符串')
        return None

    # 匹配 mount 子命令后的 remote:path 和 X: 模式
    # 思路：
    # 1. 先定位 "mount" 子命令（前面可能有带引号/不带引号的 rclone 路径）
    # 2. mount 之后提取 remote:path 参数（remote 名称为冒号前的部分）
    # 3. 提取盘符 X:（单个大写字母后跟冒号，且后面是空格或行尾）
    #
    # 正则说明：
    # \bmount\s+       - 匹配 mount 子命令及其后的空白
    # ([A-Za-z0-9_][A-Za-z0-9_.@\-]*):  - 远程名称（至少1个字符）后跟冒号
    # \S*              - 可选的路径部分（非空白字符）
    # \s+              - 分隔空白
    # ([A-Z]):         - 盘符：单个大写字母后跟冒号
    # (?:\s|$)         - 盘符后面是空格或行尾（确保不是路径的一部分）
    pattern = re.compile(
        r'\bmount\s+'
        r'([A-Za-z0-9_][A-Za-z0-9_.@\-]*):'  # 捕获组1: 远程名称
        r'\S*'                                  # 可选路径（如 :path/subdir）
        r'\s+'
        r'([A-Z]):'                             # 捕获组2: 盘符
        r'(?:\s|$)',                             # 盘符后是空格或行尾
        re.IGNORECASE
    )

    match = pattern.search(cmdline)
    if not match:
        logger.debug(f'命令行解析失败: 未匹配到 mount remote:path X: 模式, cmdline={cmdline!r}')
        return None

    remote_name = match.group(1)
    drive_letter = match.group(2).upper()

    return (drive_letter, remote_name)


class MountWorker(QThread):
    started = Signal(str)
    finished = Signal(str, bool, str)

    def __init__(self, rclone: RClone, mount: Mount):
        super().__init__()
        self.rclone = rclone
        self.mount = mount
        self.process: Optional[subprocess.Popen] = None

    def run(self):
        self.started.emit(self.mount.remote_name)

        if not self.mount.remote_name or not self.mount.drive_letter:
            self.finished.emit(self.mount.remote_name, False, "Invalid mount configuration")
            return

        cmd = [
            self.rclone.rclone_path,
            'mount',
            self.mount.remote_full_path,
            f'{self.mount.drive_letter}:',
            '--vfs-cache-mode', self.mount.cache_mode,
            '--vfs-cache-max-size', self.mount.vfs_cache_max_size,
        ]

        if self.rclone.config_path:
            cmd.extend(['--config', self.rclone.config_path])

        if self.mount.read_only:
            cmd.append('--read-only')

        cache_dir = get_cache_dir()
        if cache_dir:
            cmd.extend(['--cache-dir', cache_dir])

        import tempfile
        stderr_file = None
        try:
            stderr_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.log')

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            self.mount.process_id = self.process.pid
            self.finished.emit(self.mount.remote_name, True, "Mounted successfully")
        except Exception as e:
            error_msg = str(e)
            if stderr_file:
                try:
                    stderr_file.seek(0)
                    stderr_content = stderr_file.read()
                    if stderr_content:
                        error_msg = f"{e}: {stderr_content}"
                except Exception:
                    pass
            self.finished.emit(self.mount.remote_name, False, error_msg)
        finally:
            if stderr_file:
                try:
                    stderr_file.close()
                    os.unlink(stderr_file.name)
                except Exception:
                    pass

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            except (ProcessLookupError, OSError):
                pass
            finally:
                self.process = None


class MountManager(QObject):

    mountStatusChanged = Signal(str, MountStatus)
    mountError = Signal(str, str)

    def __init__(self, rclone: Optional[RClone] = None):
        super().__init__()
        self.rclone = rclone or RClone()
        self.mounts: Dict[str, Mount] = {}
        self.workers: Dict[str, MountWorker] = {}
        self._lock = Lock()
        self._config_file = APP_PATH / "config" / "mounts.json"
        self._shutdown = False

    def load_mounts(self):
        if self._config_file.exists():
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    with self._lock:
                        for mount_data in data:
                            mount = Mount.from_dict(mount_data)
                            self.mounts[mount.remote_name] = mount
                logger.info(f'已加载 {len(self.mounts)} 个挂载配置')

                self.refresh_mount_status()
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f'加载挂载配置失败: {e}')

    def refresh_mount_status(self):
        with self._lock:
            mounts_copy = list(self.mounts.values())

        for mount in mounts_copy:
            was_mounted = mount.status == MountStatus.MOUNTED
            is_mounted = mount.check_drive_exists()

            if is_mounted != was_mounted:
                with self._lock:
                    if is_mounted:
                        mount.status = MountStatus.MOUNTED
                        logger.debug(f'检测到挂载已存在: {mount.remote_name} -> {mount.drive_letter}:')
                    else:
                        mount.status = MountStatus.UNMOUNTED
                        mount.process_id = None
                        logger.debug(f'检测到挂载已断开: {mount.remote_name}')

        # 发现系统挂载
        discovered = self.discover_system_mounts()
        with self._lock:
            # 移除已不存在的旧 discovered 挂载
            old_discovered = [k for k, m in self.mounts.items()
                              if m.source == "discovered"]
            for key in old_discovered:
                del self.mounts[key]
            # 添加新发现的挂载
            for mount in discovered:
                key = f"_discovered_{mount.drive_letter}"
                self.mounts[key] = mount


    def save_mounts(self):
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._lock:
                data = [m.to_dict() for m in self.mounts.values()
                        if m.source == "config"]
            # 过滤掉 to_dict() 返回 None 的条目（防御性处理）
            data = [d for d in data if d is not None]
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f'已保存 {len(data)} 个挂载配置')
        except Exception as e:
            logger.error(f'保存挂载配置失败: {e}')


    def get_available_drives(self) -> List[str]:
        if os.name != 'nt':
            return []

        used = set()
        for drive in string.ascii_uppercase:
            if os.path.exists(f'{drive}:'):
                used.add(drive)

        for mount in self.mounts.values():
            if mount.is_mounted:
                used.add(mount.drive_letter)

        available = [d for d in string.ascii_uppercase if d not in used]
        return available

    def add_mount(self, remote_name: str, remote_path: str = '', drive_letter: str = '',
                  auto_mount: bool = False, **options) -> Mount:
        if not drive_letter:
            available = self.get_available_drives()
            if not available:
                raise ValueError("No available drive letters")
            drive_letter = available[0]

        mount = Mount(
            remote_name=remote_name,
            remote_path=remote_path,
            drive_letter=drive_letter,
            auto_mount=auto_mount,
            **options
        )
        with self._lock:
            self.mounts[remote_name] = mount
        self.save_mounts()
        return mount

    def remove_mount(self, remote_name: str):
        with self._lock:
            mount = self.mounts.get(remote_name)
        if mount:
            if mount.is_mounted:
                self.unmount(remote_name)
            with self._lock:
                del self.mounts[remote_name]
            self.save_mounts()

    def mount(self, remote_name: str) -> bool:
        with self._lock:
            mount = self.mounts.get(remote_name)
        if not mount:
            logger.warning(f'挂载失败: 远程存储 {remote_name} 不存在')
            return False

        if mount.is_mounted:
            logger.debug(f'远程存储 {remote_name} 已经挂载')
            return True

        logger.info(f'开始挂载 {remote_name} 到 {mount.drive_letter}: 盘')
        mount.status = MountStatus.MOUNTING
        self.mountStatusChanged.emit(remote_name, MountStatus.MOUNTING)

        worker = MountWorker(self.rclone, mount)
        worker.started.connect(self._on_mount_started)
        worker.finished.connect(self._on_mount_finished)
        with self._lock:
            self.workers[remote_name] = worker
        worker.start()

        return True

    def unmount(self, remote_name: str) -> bool:
        with self._lock:
            mount = self.mounts.get(remote_name)
        if not mount:
            return False

        logger.info(f'卸载远程存储 {remote_name} ({mount.drive_letter}: 盘)')

        terminated = False

        with self._lock:
            worker = self.workers.pop(remote_name, None)
        if worker:
            worker.stop()
            terminated = True

        if mount.process_id:
            try:
                self._terminate_process_gracefully(mount.process_id)
                logger.debug(f'已终止挂载进程 PID {mount.process_id}')
                terminated = True
            except Exception as e:
                logger.warning(f'终止挂载进程失败: {e}')
            mount.process_id = None

        # 后备机制：当 worker 和 process_id 都不可用时（如应用重启后），
        # 通过查找命令行中包含该盘符的 rclone 进程来终止
        if not terminated:
            killed = self._kill_rclone_mount_by_drive(mount.drive_letter)
            if killed:
                logger.info(f'通过盘符匹配终止了 rclone 挂载进程: {mount.drive_letter}:')
            else:
                logger.warning(f'未找到 {mount.drive_letter}: 盘对应的 rclone 挂载进程')

        mount.status = MountStatus.UNMOUNTED
        self.mountStatusChanged.emit(remote_name, MountStatus.UNMOUNTED)
        return True

    def _kill_rclone_mount_by_drive(self, drive_letter: str) -> bool:
        """通过盘符查找并终止对应的 rclone mount 进程。

        当应用重启后丢失了 worker 和 process_id 时使用此后备方法。
        策略：
        1. 优先使用 PowerShell Get-CimInstance 精确匹配命令行中的盘符
        2. 若 PowerShell 不可用，回退到 tasklist + taskkill 终止所有 rclone 进程
        """
        if os.name != 'nt':
            return False

        # 策略1：PowerShell 精确匹配（使用完整路径避免 PATH 问题）
        killed = self._kill_by_powershell(drive_letter)
        if killed:
            return True

        # 策略2：tasklist + taskkill 回退（终止所有 rclone 进程）
        return self._kill_by_tasklist(drive_letter)

    def _kill_by_powershell(self, drive_letter: str) -> bool:
        """使用 PowerShell Get-CimInstance 精确查找并终止 rclone mount 进程。"""
        # 使用完整路径，避免 PATH 中找不到 powershell 的问题
        ps_paths = [
            os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                         'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
            'powershell.exe',  # 回退到 PATH 查找
        ]

        ps_cmd = (
            f"Get-CimInstance Win32_Process -Filter "
            f"\"name like 'rclone%' and commandline like '%mount%' "
            f"and commandline like '%{drive_letter}:%'\" "
            f"| Select-Object -ExpandProperty ProcessId"
        )

        for ps_path in ps_paths:
            try:
                result = subprocess.run(
                    [ps_path, '-NoProfile', '-Command', ps_cmd],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10
                )

                pids = []
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        try:
                            pids.append(int(line))
                        except ValueError:
                            pass

                if not pids:
                    return False

                for pid in pids:
                    try:
                        self._terminate_process_gracefully(pid)
                        logger.debug(f'已终止 rclone 挂载进程 PID {pid} (盘符 {drive_letter}:)')
                    except Exception as e:
                        logger.warning(f'终止 rclone 进程 PID {pid} 失败: {e}')

                return True

            except FileNotFoundError:
                logger.debug(f'PowerShell 路径不可用: {ps_path}')
                continue
            except Exception as e:
                logger.debug(f'PowerShell 查询失败 ({ps_path}): {e}')
                continue

        return False

    def _query_rclone_mount_processes(self) -> List[tuple]:
        """通过 PowerShell 查询所有 rclone mount 进程。

        使用 Get-CimInstance Win32_Process 查询命令行中包含 mount 的 rclone 进程，
        解析输出提取盘符、PID 和远程存储名称。

        复用 _kill_by_powershell 的 PowerShell 路径回退策略：
        优先使用完整路径，回退到 PATH 查找。

        Returns:
            [(drive_letter, pid, remote_name), ...] 的列表，失败时返回空列表。
        """
        # 使用完整路径，避免 PATH 中找不到 powershell 的问题
        ps_paths = [
            os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                         'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
            'powershell.exe',  # 回退到 PATH 查找
        ]

        ps_cmd = (
            "Get-CimInstance Win32_Process -Filter "
            "\"name like 'rclone%' and commandline like '%mount%'\" "
            "| Select-Object ProcessId, CommandLine "
            "| ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"
        )

        for ps_path in ps_paths:
            try:
                result = subprocess.run(
                    [ps_path, '-NoProfile', '-Command', ps_cmd],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10
                )

                processes = []
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if not line or '|' not in line:
                        continue

                    # 解析 "PID|CommandLine" 格式
                    sep_index = line.index('|')
                    pid_str = line[:sep_index].strip()
                    cmdline = line[sep_index + 1:].strip()

                    try:
                        pid = int(pid_str)
                    except ValueError:
                        logger.debug(f'跳过无效 PID: {pid_str!r}')
                        continue

                    # 使用现有的命令行解析函数提取盘符和远程名称
                    parsed = _parse_rclone_mount_cmdline(cmdline)
                    if parsed is None:
                        logger.debug(f'跳过无法解析的命令行: {cmdline!r}')
                        continue

                    drive_letter, remote_name = parsed
                    processes.append((drive_letter, pid, remote_name))

                return processes

            except FileNotFoundError:
                logger.debug(f'PowerShell 路径不可用: {ps_path}')
                continue
            except subprocess.TimeoutExpired:
                logger.warning(f'PowerShell 查询超时 ({ps_path})')
                continue
            except Exception as e:
                logger.warning(f'PowerShell 查询失败 ({ps_path}): {e}')
                continue

        logger.warning('所有 PowerShell 路径均不可用，无法查询 rclone mount 进程')
        return []

    def discover_system_mounts(self) -> List[Mount]:
        """扫描系统中运行的 rclone mount 进程，返回不在配置中的发现挂载列表。

        仅在 Windows 平台执行，非 Windows 平台直接返回空列表。
        通过 _query_rclone_mount_processes 查询系统进程，过滤掉已在配置中的盘符，
        为未知盘符创建 source="discovered" 的 Mount 对象。

        Returns:
            不在配置中的发现挂载列表。
        """
        if os.name != 'nt':
            return []

        discovered = []
        processes = self._query_rclone_mount_processes()
        config_drives = {m.drive_letter for m in self.mounts.values()
                         if m.source == "config"}

        for drive_letter, pid, remote_name in processes:
            if drive_letter not in config_drives:
                mount = Mount.from_process_info(drive_letter, pid, remote_name)
                discovered.append(mount)

        return discovered


    def _kill_by_tasklist(self, drive_letter: str) -> bool:
        """使用 tasklist/taskkill 回退方案终止 rclone 进程。

        tasklist 无法显示命令行参数，因此只能按进程名匹配。
        仅在确认盘符仍被占用时才执行终止。
        """
        try:
            # 确认目标盘符确实存在（说明 rclone 进程仍在运行）
            if not os.path.exists(f'{drive_letter}:'):
                return False

            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq rclone.exe', '/NH'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10
            )

            if 'rclone' not in result.stdout.lower():
                return False

            # 使用 taskkill 终止 rclone.exe（不带 /T 避免误杀其他 rclone 操作）
            subprocess.run(
                ['taskkill', '/F', '/IM', 'rclone.exe'],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10
            )
            logger.info(f'通过 taskkill 终止了 rclone 进程 (盘符 {drive_letter}:)')
            return True

        except Exception as e:
            logger.warning(f'tasklist/taskkill 回退失败: {e}')
            return False



    def unmount_all(self):
        logger.info('卸载所有挂载')
        with self._lock:
            remote_names = list(self.mounts.keys())
        for remote_name in remote_names:
            self.unmount(remote_name)

    def auto_mount_all(self):
        with self._lock:
            auto_mounts = [m for m in self.mounts.values() if m.auto_mount and not m.is_mounted]
        logger.info(f'自动挂载 {len(auto_mounts)} 个远程存储')
        success_count = 0
        fail_count = 0
        for mount in auto_mounts:
            try:
                success = self.mount(mount.remote_name)
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    logger.warning(f'自动挂载失败: {mount.remote_name}')
            except Exception as e:
                fail_count += 1
                logger.error(f'自动挂载出错: {mount.remote_name} - {e}')
        if fail_count > 0:
            logger.warning(f'自动挂载完成: {success_count} 成功, {fail_count} 失败')

    def _terminate_process_gracefully(self, process_id: int, timeout: int = 5) -> bool:
        try:
            if os.name == 'nt':
                result = subprocess.run(
                    ['taskkill', '/PID', str(process_id)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=timeout
                )

                for _ in range(timeout * 10):
                    time.sleep(0.1)
                    if not self._is_process_running(process_id):
                        return True

                subprocess.run(
                    ['taskkill', '/F', '/PID', str(process_id)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                os.kill(process_id, signal.SIGTERM)

                for _ in range(timeout * 10):
                    time.sleep(0.1)
                    if not self._is_process_running(process_id):
                        return True

                os.kill(process_id, signal.SIGKILL)

            return True
        except Exception as e:
            logger.warning(f'终止进程 {process_id} 失败: {e}')
            return False

    def _is_process_running(self, process_id: int) -> bool:
        try:
            if os.name == 'nt':
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {process_id}'],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return str(process_id) in result.stdout.decode()
            else:
                os.kill(process_id, 0)
                return True
        except (ProcessLookupError, OSError):
            return False

    def _on_mount_started(self, remote_name: str):
        try:
            with self._lock:
                mount = self.mounts.get(remote_name)
            if mount:
                mount.status = MountStatus.MOUNTING
                self.mountStatusChanged.emit(remote_name, MountStatus.MOUNTING)
        except Exception as e:
            logger.error(f'处理挂载开始信号时出错: {e}')

    def _on_mount_finished(self, remote_name: str, success: bool, message: str):
        try:
            with self._lock:
                mount = self.mounts.get(remote_name)
            if mount:
                if success:
                    mount.status = MountStatus.MOUNTED
                    mount.error_message = None
                    logger.info(f'挂载成功: {remote_name} -> {mount.drive_letter}: 盘')
                else:
                    mount.status = MountStatus.ERROR
                    mount.error_message = message
                    self.mountError.emit(remote_name, message)
                    logger.error(f'挂载失败: {remote_name} - {message}')

                self.mountStatusChanged.emit(remote_name, mount.status)
        except Exception as e:
            logger.error(f'处理挂载完成信号时出错: {e}')
