"""MountManager 发现逻辑单元测试。

测试 _query_rclone_mount_processes、discover_system_mounts、
refresh_mount_status 集成发现、save_mounts 过滤 discovered 挂载。

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

import json
import os
import subprocess
from pathlib import Path
from threading import Lock
from unittest.mock import MagicMock

import pytest


class TestQueryRcloneMountProcesses:
    """测试 _query_rclone_mount_processes 方法。"""

    @pytest.fixture
    def manager(self, tmp_path, mocker):
        """创建不依赖 QObject 的 MountManager 实例。"""
        from app.core.mount_manager import MountManager
        mgr = MountManager.__new__(MountManager)
        mgr._lock = Lock()
        mgr.mounts = {}
        mgr.workers = {}
        mgr._config_file = tmp_path / "mounts.json"
        mgr._shutdown = False
        mgr.rclone = MagicMock()
        return mgr

    def test_successful_query_multiple_processes(self, manager, mocker):
        """测试 PowerShell 查询成功返回多个 rclone 进程。"""
        ps_output = (
            "1234|rclone mount myremote: X: --vfs-cache-mode full\n"
            "5678|rclone mount gdrive:docs Z:\n"
        )
        mock_run = mocker.patch('subprocess.run', return_value=MagicMock(
            stdout=ps_output, stderr='', returncode=0
        ))

        result = manager._query_rclone_mount_processes()

        assert len(result) == 2
        assert result[0] == ('X', 1234, 'myremote')
        assert result[1] == ('Z', 5678, 'gdrive')
        mock_run.assert_called_once()

    def test_empty_output_no_processes(self, manager, mocker):
        """测试 PowerShell 查询返回空输出（无 rclone 进程）。"""
        mock_run = mocker.patch('subprocess.run', return_value=MagicMock(
            stdout='', stderr='', returncode=0
        ))

        result = manager._query_rclone_mount_processes()

        assert result == []
        mock_run.assert_called_once()

    def test_first_path_fails_fallback_to_second(self, manager, mocker):
        """测试第一个 PowerShell 路径失败（FileNotFoundError），回退到第二个路径。"""
        ps_output = "9999|rclone mount backup: Y:\n"

        def side_effect(cmd, **kwargs):
            if 'System32' in str(cmd[0]):
                raise FileNotFoundError("powershell not found at full path")
            return MagicMock(stdout=ps_output, stderr='', returncode=0)

        mock_run = mocker.patch('subprocess.run', side_effect=side_effect)

        result = manager._query_rclone_mount_processes()

        assert len(result) == 1
        assert result[0] == ('Y', 9999, 'backup')
        assert mock_run.call_count == 2

    def test_timeout_returns_empty(self, manager, mocker):
        """测试 PowerShell 查询超时（subprocess.TimeoutExpired）。"""
        mocker.patch('subprocess.run',
                     side_effect=subprocess.TimeoutExpired(cmd='powershell', timeout=10))

        result = manager._query_rclone_mount_processes()

        assert result == []

    def test_general_exception_returns_empty(self, manager, mocker):
        """测试 PowerShell 查询一般异常。"""
        mocker.patch('subprocess.run',
                     side_effect=Exception("unexpected error"))

        result = manager._query_rclone_mount_processes()

        assert result == []

    def test_malformed_output_invalid_pid(self, manager, mocker):
        """测试输出中包含无效 PID 的行被跳过。"""
        ps_output = (
            "notanumber|rclone mount myremote: X:\n"
            "1234|rclone mount gdrive: Z:\n"
        )
        mocker.patch('subprocess.run', return_value=MagicMock(
            stdout=ps_output, stderr='', returncode=0
        ))

        result = manager._query_rclone_mount_processes()

        assert len(result) == 1
        assert result[0] == ('Z', 1234, 'gdrive')

    def test_malformed_output_missing_separator(self, manager, mocker):
        """测试输出中缺少分隔符的行被跳过。"""
        ps_output = (
            "this line has no pipe separator\n"
            "5678|rclone mount backup: W:\n"
        )
        mocker.patch('subprocess.run', return_value=MagicMock(
            stdout=ps_output, stderr='', returncode=0
        ))

        result = manager._query_rclone_mount_processes()

        assert len(result) == 1
        assert result[0] == ('W', 5678, 'backup')


class TestDiscoverSystemMounts:
    """测试 discover_system_mounts 方法。"""

    @pytest.fixture
    def manager(self, tmp_path, mocker):
        from app.core.mount_manager import MountManager
        mgr = MountManager.__new__(MountManager)
        mgr._lock = Lock()
        mgr.mounts = {}
        mgr.workers = {}
        mgr._config_file = tmp_path / "mounts.json"
        mgr._shutdown = False
        mgr.rclone = MagicMock()
        return mgr

    def test_non_windows_returns_empty(self, manager, mocker):
        """测试非 Windows 平台直接返回空列表。"""
        mocker.patch('os.name', 'posix')

        result = manager.discover_system_mounts()

        assert result == []

    def test_filters_out_config_drives(self, manager, mocker):
        """测试过滤掉已在配置中的盘符。"""
        from app.models.mount import Mount
        mocker.patch('os.name', 'nt')

        # 配置中已有 X 盘
        config_mount = Mount(remote_name='existing', remote_path='', drive_letter='X')
        manager.mounts = {'existing': config_mount}

        # 系统中发现 X 和 Y 两个进程
        mocker.patch.object(manager, '_query_rclone_mount_processes',
                            return_value=[('X', 1234, 'remote1'), ('Y', 5678, 'remote2')])

        result = manager.discover_system_mounts()

        assert len(result) == 1
        assert result[0].drive_letter == 'Y'
        assert result[0].source == 'discovered'

    def test_returns_discovered_mounts_with_correct_attributes(self, manager, mocker):
        """测试返回的发现挂载具有正确的属性。"""
        from app.models.mount import MountStatus
        mocker.patch('os.name', 'nt')

        mocker.patch.object(manager, '_query_rclone_mount_processes',
                            return_value=[('Z', 4321, 'mycloud')])

        result = manager.discover_system_mounts()

        assert len(result) == 1
        mount = result[0]
        assert mount.drive_letter == 'Z'
        assert mount.process_id == 4321
        assert mount.remote_name == 'mycloud'
        assert mount.source == 'discovered'
        assert mount.status == MountStatus.MOUNTED


class TestRefreshMountStatusDiscovery:
    """测试 refresh_mount_status 集成发现逻辑。"""

    @pytest.fixture
    def manager(self, tmp_path, mocker):
        from app.core.mount_manager import MountManager
        mgr = MountManager.__new__(MountManager)
        mgr._lock = Lock()
        mgr.mounts = {}
        mgr.workers = {}
        mgr._config_file = tmp_path / "mounts.json"
        mgr._shutdown = False
        mgr.rclone = MagicMock()
        return mgr

    def test_adds_discovered_mounts_with_prefix(self, manager, mocker):
        """测试 refresh_mount_status 将发现挂载以 _discovered_ 前缀添加到 mounts 字典。"""
        from app.models.mount import Mount, MountStatus

        # Mock check_drive_exists 避免真实磁盘检测
        mocker.patch.object(Mount, 'check_drive_exists', return_value=False)

        discovered_mount = Mount.from_process_info('Z', 9999, 'cloud')
        mocker.patch.object(manager, 'discover_system_mounts',
                            return_value=[discovered_mount])

        manager.refresh_mount_status()

        assert '_discovered_Z' in manager.mounts
        assert manager.mounts['_discovered_Z'].source == 'discovered'
        assert manager.mounts['_discovered_Z'].drive_letter == 'Z'

    def test_clears_old_discovered_before_adding_new(self, manager, mocker):
        """测试 refresh_mount_status 在添加新发现挂载前清除旧的 discovered 挂载。"""
        from app.models.mount import Mount, MountStatus

        mocker.patch.object(Mount, 'check_drive_exists', return_value=False)

        # 预先放入旧的 discovered 挂载
        old_mount = Mount.from_process_info('W', 1111, 'old_remote')
        manager.mounts['_discovered_W'] = old_mount

        # 新发现的挂载是 Y 盘
        new_mount = Mount.from_process_info('Y', 2222, 'new_remote')
        mocker.patch.object(manager, 'discover_system_mounts',
                            return_value=[new_mount])

        manager.refresh_mount_status()

        # 旧的 W 应该被清除
        assert '_discovered_W' not in manager.mounts
        # 新的 Y 应该被添加
        assert '_discovered_Y' in manager.mounts
        assert manager.mounts['_discovered_Y'].remote_name == 'new_remote'


class TestSaveMountsDiscoveredFilter:
    """测试 save_mounts 不保存 discovered 挂载。"""

    @pytest.fixture
    def manager(self, tmp_path, mocker):
        from app.core.mount_manager import MountManager
        mgr = MountManager.__new__(MountManager)
        mgr._lock = Lock()
        mgr.mounts = {}
        mgr.workers = {}
        mgr._config_file = tmp_path / "mounts.json"
        mgr._shutdown = False
        mgr.rclone = MagicMock()
        return mgr

    def test_save_mounts_excludes_discovered(self, manager):
        """测试 save_mounts 只保存 config 挂载，不保存 discovered 挂载。"""
        from app.models.mount import Mount

        config_mount = Mount(remote_name='myremote', remote_path='', drive_letter='X')
        discovered_mount = Mount.from_process_info('Z', 9999, 'external')

        manager.mounts = {
            'myremote': config_mount,
            '_discovered_Z': discovered_mount,
        }

        manager.save_mounts()

        # 读取保存的文件验证
        with open(manager._config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]['remote_name'] == 'myremote'
        # 确保没有 discovered 挂载被保存
        for item in data:
            assert item.get('source', 'config') != 'discovered'
