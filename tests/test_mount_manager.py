import pytest
import json
import os
from unittest.mock import MagicMock, patch, PropertyMock


class TestMountManager:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = 'rclone.exe'
        rclone.config_path = None
        return rclone

    @pytest.fixture
    def mount_manager(self, mock_rclone, tmp_path, mocker):
        from app.core.mount_manager import MountManager
        mocker.patch('app.core.mount_manager.APP_PATH', tmp_path)
        manager = MountManager(mock_rclone)
        manager._config_file = tmp_path / "config" / "mounts.json"
        # Mock 掉发现逻辑，避免真实系统进程干扰测试
        mocker.patch.object(manager, 'discover_system_mounts', return_value=[])
        return manager

    def test_init(self, mount_manager):
        assert mount_manager.mounts == {}
        assert mount_manager.workers == {}

    def test_load_mounts_no_file(self, mount_manager):
        mount_manager.load_mounts()
        assert mount_manager.mounts == {}

    def test_load_mounts_with_file(self, mount_manager):
        mount_manager._config_file.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {'remote_name': 'test1', 'remote_path': '/', 'drive_letter': 'X'},
            {'remote_name': 'test2', 'remote_path': '/docs', 'drive_letter': 'Y'}
        ]
        with open(mount_manager._config_file, 'w') as f:
            json.dump(data, f)

        mount_manager.load_mounts()

        assert len(mount_manager.mounts) == 2
        assert 'test1' in mount_manager.mounts
        assert 'test2' in mount_manager.mounts

    def test_load_mounts_invalid_json(self, mount_manager):
        mount_manager._config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mount_manager._config_file, 'w') as f:
            f.write('invalid json')

        mount_manager.load_mounts()
        assert mount_manager.mounts == {}

    def test_save_mounts(self, mount_manager):
        from app.models.mount import Mount
        mount_manager.mounts['test'] = Mount(
            remote_name='test',
            remote_path='/path',
            drive_letter='Z'
        )

        mount_manager.save_mounts()

        assert mount_manager._config_file.exists()
        with open(mount_manager._config_file, 'r') as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]['remote_name'] == 'test'

    @patch('os.path.exists')
    def test_get_available_drives_windows(self, mock_exists, mount_manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_exists.side_effect = lambda x: x in ['C:', 'D:']

        drives = mount_manager.get_available_drives()

        assert 'C' not in drives
        assert 'D' not in drives
        assert 'E' in drives
        assert 'Z' in drives

    def test_get_available_drives_non_windows(self, mount_manager, mocker):
        mocker.patch('os.name', 'posix')

        drives = mount_manager.get_available_drives()

        assert drives == []

    @patch('os.path.exists')
    def test_get_available_drives_excludes_mounted(self, mock_exists, mount_manager, mocker):
        from unittest.mock import PropertyMock
        from app.models.mount import Mount, MountStatus
        mock_exists.return_value = False

        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.MOUNTED
        type(mount).is_mounted = PropertyMock(return_value=True)
        mount_manager.mounts['test'] = mount

        drives = mount_manager.get_available_drives()

        assert 'X' not in drives

    @patch('os.path.exists')
    def test_add_mount(self, mock_exists, mount_manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_exists.return_value = False

        mount = mount_manager.add_mount(
            remote_name='myremote',
            remote_path='/docs',
            drive_letter='Z',
            auto_mount=True
        )

        assert mount.remote_name == 'myremote'
        assert mount.remote_path == '/docs'
        assert mount.drive_letter == 'Z'
        assert mount.auto_mount is True
        assert 'myremote' in mount_manager.mounts

    @patch('os.path.exists')
    def test_add_mount_auto_drive(self, mock_exists, mount_manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_exists.side_effect = lambda x: x[0] != 'Z'

        mount = mount_manager.add_mount(remote_name='test', remote_path='')

        assert mount.drive_letter == 'Z'

    @patch('os.path.exists')
    def test_add_mount_no_available_drives(self, mock_exists, mount_manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_exists.return_value = True

        with pytest.raises(ValueError, match="No available drive letters"):
            mount_manager.add_mount(remote_name='test', remote_path='')

    def test_remove_mount(self, mount_manager):
        from app.models.mount import Mount
        mount_manager.mounts['test'] = Mount(
            remote_name='test', remote_path='', drive_letter='X'
        )

        mount_manager.remove_mount('test')

        assert 'test' not in mount_manager.mounts

    def test_remove_mount_unmounts_first(self, mount_manager, mocker):
        from unittest.mock import PropertyMock
        from app.models.mount import Mount, MountStatus
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.MOUNTED
        type(mount).is_mounted = PropertyMock(return_value=True)
        mount_manager.mounts['test'] = mount

        unmount_mock = mocker.patch.object(mount_manager, 'unmount')
        mount_manager.remove_mount('test')

        unmount_mock.assert_called_once_with('test')

    def test_mount_not_found(self, mount_manager):
        result = mount_manager.mount('nonexistent')
        assert result is False

    def test_mount_already_mounted(self, mount_manager):
        from app.models.mount import Mount, MountStatus
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.MOUNTED
        mount_manager.mounts['test'] = mount

        result = mount_manager.mount('test')

        assert result is True

    def test_unmount_not_found(self, mount_manager):
        result = mount_manager.unmount('nonexistent')
        assert result is False

    @patch('subprocess.run')
    def test_unmount_kills_process(self, mock_run, mount_manager, mocker):
        from app.models.mount import Mount, MountStatus
        mocker.patch('os.name', 'nt')

        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.MOUNTED
        mount.process_id = 12345
        mount_manager.mounts['test'] = mount

        result = mount_manager.unmount('test')

        assert result is True
        assert mount.status == MountStatus.UNMOUNTED
        assert mount.process_id is None

    def test_unmount_stops_worker(self, mount_manager):
        from app.models.mount import Mount
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount_manager.mounts['test'] = mount

        worker_mock = MagicMock()
        mount_manager.workers['test'] = worker_mock

        mount_manager.unmount('test')

        worker_mock.stop.assert_called_once()
        assert 'test' not in mount_manager.workers

    def test_unmount_fallback_kills_by_drive(self, mount_manager, mocker):
        """当 worker 和 process_id 都不可用时，通过盘符查找 rclone 进程"""
        from app.models.mount import Mount, MountStatus
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.MOUNTED
        mount.process_id = None
        mount_manager.mounts['test'] = mount

        kill_mock = mocker.patch.object(mount_manager, '_kill_rclone_mount_by_drive', return_value=True)

        result = mount_manager.unmount('test')

        assert result is True
        assert mount.status == MountStatus.UNMOUNTED
        kill_mock.assert_called_once_with('X')

    def test_unmount_no_fallback_when_worker_exists(self, mount_manager, mocker):
        """有 worker 时不应触发后备机制"""
        from app.models.mount import Mount
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount_manager.mounts['test'] = mount

        worker_mock = MagicMock()
        mount_manager.workers['test'] = worker_mock

        kill_mock = mocker.patch.object(mount_manager, '_kill_rclone_mount_by_drive')

        mount_manager.unmount('test')

        worker_mock.stop.assert_called_once()
        kill_mock.assert_not_called()

    def test_kill_rclone_mount_by_drive_powershell_finds_pid(self, mount_manager, mocker):
        """PowerShell 策略能正确解析 PID 输出并终止进程"""
        mocker.patch('os.name', 'nt')
        ps_mock = mocker.patch.object(mount_manager, '_kill_by_powershell', return_value=True)

        result = mount_manager._kill_rclone_mount_by_drive('B')

        assert result is True
        ps_mock.assert_called_once_with('B')

    def test_kill_rclone_mount_by_drive_fallback_to_tasklist(self, mount_manager, mocker):
        """PowerShell 失败时回退到 tasklist/taskkill"""
        mocker.patch('os.name', 'nt')
        mocker.patch.object(mount_manager, '_kill_by_powershell', return_value=False)
        tasklist_mock = mocker.patch.object(mount_manager, '_kill_by_tasklist', return_value=True)

        result = mount_manager._kill_rclone_mount_by_drive('B')

        assert result is True
        tasklist_mock.assert_called_once_with('B')

    def test_kill_rclone_mount_by_drive_no_match(self, mount_manager, mocker):
        """两种策略都没有匹配时返回 False"""
        mocker.patch('os.name', 'nt')
        mocker.patch.object(mount_manager, '_kill_by_powershell', return_value=False)
        mocker.patch.object(mount_manager, '_kill_by_tasklist', return_value=False)

        result = mount_manager._kill_rclone_mount_by_drive('Z')

        assert result is False

    def test_kill_rclone_mount_by_drive_non_windows(self, mount_manager, mocker):
        """非 Windows 系统直接返回 False"""
        mocker.patch('os.name', 'posix')

        result = mount_manager._kill_rclone_mount_by_drive('X')

        assert result is False

    def test_kill_by_powershell_finds_pid(self, mount_manager, mocker):
        """_kill_by_powershell 能正确解析 PowerShell 输出并终止进程"""
        mock_run = mocker.patch('subprocess.run')
        mock_run.return_value = MagicMock(stdout='9999\r\n', returncode=0)
        term_mock = mocker.patch.object(mount_manager, '_terminate_process_gracefully')

        result = mount_manager._kill_by_powershell('B')

        assert result is True
        term_mock.assert_called_once_with(9999)

    def test_kill_by_powershell_no_match(self, mount_manager, mocker):
        """PowerShell 没有匹配进程时返回 False"""
        mock_run = mocker.patch('subprocess.run')
        mock_run.return_value = MagicMock(stdout='\r\n', returncode=0)

        result = mount_manager._kill_by_powershell('Z')

        assert result is False

    def test_kill_by_powershell_file_not_found_tries_fallback_path(self, mount_manager, mocker):
        """第一个 PowerShell 路径不存在时尝试第二个路径"""
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise FileNotFoundError("powershell not found")
            return MagicMock(stdout='8888\r\n', returncode=0)

        mocker.patch('subprocess.run', side_effect=side_effect)
        term_mock = mocker.patch.object(mount_manager, '_terminate_process_gracefully')

        result = mount_manager._kill_by_powershell('X')

        assert result is True
        term_mock.assert_called_once_with(8888)

    def test_kill_by_powershell_all_paths_fail(self, mount_manager, mocker):
        """所有 PowerShell 路径都不可用时返回 False"""
        mocker.patch('subprocess.run', side_effect=FileNotFoundError("not found"))

        result = mount_manager._kill_by_powershell('X')

        assert result is False

    def test_kill_by_tasklist_finds_rclone(self, mount_manager, mocker):
        """tasklist 找到 rclone 进程且盘符存在时执行 taskkill"""
        mocker.patch('os.path.exists', return_value=True)
        mock_run = mocker.patch('subprocess.run')
        mock_run.return_value = MagicMock(stdout='rclone.exe  9999 Console  1  30,000 K\r\n')

        result = mount_manager._kill_by_tasklist('B')

        assert result is True
        # 应该调用了 tasklist 和 taskkill
        assert mock_run.call_count == 2

    def test_kill_by_tasklist_drive_not_exists(self, mount_manager, mocker):
        """盘符不存在时直接返回 False（无需 taskkill）"""
        mocker.patch('os.path.exists', return_value=False)

        result = mount_manager._kill_by_tasklist('Z')

        assert result is False

    def test_kill_by_tasklist_no_rclone_process(self, mount_manager, mocker):
        """盘符存在但没有 rclone 进程时返回 False"""
        mocker.patch('os.path.exists', return_value=True)
        mock_run = mocker.patch('subprocess.run')
        mock_run.return_value = MagicMock(stdout='INFO: No tasks are running\r\n')

        result = mount_manager._kill_by_tasklist('B')

        assert result is False

    def test_unmount_all(self, mount_manager, mocker):
        from app.models.mount import Mount
        mount_manager.mounts['test1'] = Mount(remote_name='test1', remote_path='', drive_letter='X')
        mount_manager.mounts['test2'] = Mount(remote_name='test2', remote_path='', drive_letter='Y')

        unmount_mock = mocker.patch.object(mount_manager, 'unmount')
        mount_manager.unmount_all()

        assert unmount_mock.call_count == 2

    def test_auto_mount_all(self, mount_manager, mocker):
        from unittest.mock import PropertyMock
        from app.models.mount import Mount
        mount1 = Mount(remote_name='test1', remote_path='', drive_letter='X', auto_mount=True)
        mount2 = Mount(remote_name='test2', remote_path='', drive_letter='Y', auto_mount=False)
        type(mount1).is_mounted = PropertyMock(return_value=False)
        type(mount2).is_mounted = PropertyMock(return_value=False)
        mount_manager.mounts['test1'] = mount1
        mount_manager.mounts['test2'] = mount2

        mount_mock = mocker.patch.object(mount_manager, 'mount')
        mount_manager.auto_mount_all()

        mount_mock.assert_called_once_with('test1')

    def test_on_mount_started(self, mount_manager):
        from app.models.mount import Mount, MountStatus
        mount_manager.mounts['test'] = Mount(remote_name='test', remote_path='', drive_letter='X')

        mount_manager._on_mount_started('test')

        assert mount_manager.mounts['test'].status == MountStatus.MOUNTING

    def test_on_mount_finished_success(self, mount_manager):
        from app.models.mount import Mount, MountStatus
        mount_manager.mounts['test'] = Mount(remote_name='test', remote_path='', drive_letter='X')

        mount_manager._on_mount_finished('test', True, 'Mounted successfully')

        assert mount_manager.mounts['test'].status == MountStatus.MOUNTED
        assert mount_manager.mounts['test'].error_message is None

    def test_on_mount_finished_failure(self, mount_manager):
        from app.models.mount import Mount, MountStatus
        mount_manager.mounts['test'] = Mount(remote_name='test', remote_path='', drive_letter='X')

        mount_manager._on_mount_finished('test', False, 'Mount failed')

        assert mount_manager.mounts['test'].status == MountStatus.ERROR
        assert mount_manager.mounts['test'].error_message == 'Mount failed'


class TestMountWorker:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = 'rclone.exe'
        rclone.config_path = None
        return rclone

    @pytest.fixture
    def mount(self):
        from app.models.mount import Mount
        return Mount(
            remote_name='test',
            remote_path='/docs',
            drive_letter='X',
            cache_mode='full',
            vfs_cache_max_size='5G'
        )

    def test_worker_creation(self, mock_rclone, mount):
        from app.core.mount_manager import MountWorker
        worker = MountWorker(mock_rclone, mount)

        assert worker.rclone == mock_rclone
        assert worker.mount == mount
        assert worker.process is None

    def test_worker_stop(self, mock_rclone, mount):
        from app.core.mount_manager import MountWorker
        worker = MountWorker(mock_rclone, mount)
        mock_process = MagicMock()
        worker.process = mock_process

        worker.stop()

        mock_process.terminate.assert_called_once()
        assert worker.process is None

    def test_worker_run_success(self, mock_rclone, mount):
        from app.core.mount_manager import MountWorker

        mock_rclone.rclone_path = "rclone"
        mock_rclone.config_path = "config.conf"

        worker = MountWorker(mock_rclone, mount)

        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 100
            mock_popen.return_value = mock_process

            started_signal = MagicMock()
            finished_signal = MagicMock()
            worker.started.connect(started_signal)
            worker.finished.connect(finished_signal)

            worker.run()

            assert worker.mount.process_id == 100
            started_signal.assert_called_with(mount.remote_name)
            finished_signal.assert_called_with(mount.remote_name, True, "Mounted successfully")

    def test_worker_run_failure(self, mock_rclone, mount):
        from app.core.mount_manager import MountWorker

        worker = MountWorker(mock_rclone, mount)

        with patch('subprocess.Popen', side_effect=Exception("Mount error")):
            finished_signal = MagicMock()
            worker.finished.connect(finished_signal)

            worker.run()

            finished_signal.assert_called_with(mount.remote_name, False, "Mount error")

    def test_worker_stop_no_process(self, mock_rclone, mount):
        from app.core.mount_manager import MountWorker
        worker = MountWorker(mock_rclone, mount)
        worker.process = None

        worker.stop()
        assert worker.process is None
