import pytest
import json
import os
import subprocess
from unittest.mock import MagicMock, patch, PropertyMock, mock_open


class TestMountManagerDeep:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = 'rclone.exe'
        rclone.config_path = None
        return rclone

    @pytest.fixture
    def manager(self, mock_rclone, tmp_path, mocker):
        from app.core.mount_manager import MountManager
        mocker.patch('app.core.mount_manager.APP_PATH', tmp_path)
        mgr = MountManager(mock_rclone)
        mgr._config_file = tmp_path / "config" / "mounts.json"
        return mgr


    def test_refresh_mount_status_mounted_to_unmounted(self, manager, mocker):
        from app.models.mount import Mount, MountStatus
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.MOUNTED
        mocker.patch.object(mount, 'check_drive_exists', return_value=False)
        manager.mounts['test'] = mount

        manager.refresh_mount_status()

        assert mount.status == MountStatus.UNMOUNTED
        assert mount.process_id is None

    def test_refresh_mount_status_unmounted_to_mounted(self, manager, mocker):
        from app.models.mount import Mount, MountStatus
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.UNMOUNTED
        mocker.patch.object(mount, 'check_drive_exists', return_value=True)
        manager.mounts['test'] = mount

        manager.refresh_mount_status()

        assert mount.status == MountStatus.MOUNTED

    def test_refresh_mount_status_no_change(self, manager, mocker):
        from app.models.mount import Mount, MountStatus
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.UNMOUNTED
        mocker.patch.object(mount, 'check_drive_exists', return_value=False)
        manager.mounts['test'] = mount

        manager.refresh_mount_status()

        assert mount.status == MountStatus.UNMOUNTED


    def test_save_mounts_exception(self, manager, mocker):
        from app.models.mount import Mount
        manager.mounts['test'] = Mount(remote_name='test', remote_path='', drive_letter='X')
        manager._config_file.parent.mkdir(parents=True, exist_ok=True)
        mocker.patch('builtins.open', side_effect=PermissionError("denied"))

        manager.save_mounts()


    def test_terminate_process_gracefully_windows_immediate(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_run = mocker.patch('subprocess.run')
        mocker.patch.object(manager, '_is_process_running', return_value=False)

        result = manager._terminate_process_gracefully(12345, timeout=1)

        assert result is True
        assert mock_run.call_count >= 1

    def test_terminate_process_gracefully_windows_force_kill(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_run = mocker.patch('subprocess.run')
        mocker.patch.object(manager, '_is_process_running', return_value=True)
        mocker.patch('time.sleep')

        result = manager._terminate_process_gracefully(12345, timeout=1)

        assert result is True
        force_calls = [c for c in mock_run.call_args_list if '/F' in c[0][0]]
        assert len(force_calls) >= 1

    def test_terminate_process_gracefully_posix_immediate(self, manager, mocker):
        mocker.patch('os.name', 'posix')
        mock_kill = mocker.patch('os.kill')
        mocker.patch.object(manager, '_is_process_running', return_value=False)

        result = manager._terminate_process_gracefully(12345, timeout=1)

        assert result is True
        mock_kill.assert_called()

    def test_terminate_process_gracefully_posix_force_kill(self, manager, mocker):
        import signal as signal_module
        SIGKILL = getattr(signal_module, 'SIGKILL', 9)
        mocker.patch('os.name', 'posix')
        mocker.patch('app.core.mount_manager.signal.SIGKILL', SIGKILL, create=True)
        mock_kill = mocker.patch('os.kill')
        mocker.patch.object(manager, '_is_process_running', return_value=True)
        mocker.patch('time.sleep')

        result = manager._terminate_process_gracefully(12345, timeout=1)

        assert result is True
        sigkill_calls = [c for c in mock_kill.call_args_list if c[0][1] == SIGKILL]
        assert len(sigkill_calls) >= 1

    def test_terminate_process_gracefully_exception(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mocker.patch('subprocess.run', side_effect=Exception("process error"))

        result = manager._terminate_process_gracefully(12345, timeout=1)

        assert result is False


    def test_is_process_running_windows_true(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_result = MagicMock()
        mock_result.stdout.decode.return_value = 'PID 12345 running'
        mocker.patch('subprocess.run', return_value=mock_result)

        assert manager._is_process_running(12345) is True

    def test_is_process_running_windows_false(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_result = MagicMock()
        mock_result.stdout.decode.return_value = 'No tasks found'
        mocker.patch('subprocess.run', return_value=mock_result)

        assert manager._is_process_running(12345) is False

    def test_is_process_running_posix_true(self, manager, mocker):
        mocker.patch('os.name', 'posix')
        mocker.patch('os.kill')

        assert manager._is_process_running(12345) is True

    def test_is_process_running_posix_false(self, manager, mocker):
        mocker.patch('os.name', 'posix')
        mocker.patch('os.kill', side_effect=ProcessLookupError())

        assert manager._is_process_running(12345) is False


    def test_on_mount_started_nonexistent(self, manager):
        manager._on_mount_started('nonexistent')

    def test_on_mount_started_exception(self, manager, mocker):
        from app.models.mount import Mount
        manager.mounts['test'] = Mount(remote_name='test', remote_path='', drive_letter='X')
        mocker.patch.object(manager, 'mountStatusChanged', side_effect=Exception("signal error"))

        manager._on_mount_started('test')


    def test_on_mount_finished_nonexistent(self, manager):
        manager._on_mount_finished('nonexistent', True, 'ok')

    def test_on_mount_finished_exception(self, manager, mocker):
        from app.models.mount import Mount
        manager.mounts['test'] = Mount(remote_name='test', remote_path='', drive_letter='X')
        mocker.patch.object(manager, 'mountStatusChanged', side_effect=Exception("signal error"))

        manager._on_mount_finished('test', True, 'ok')


    def test_auto_mount_all_mixed_results(self, manager, mocker):
        from app.models.mount import Mount
        mount1 = Mount(remote_name='ok', remote_path='', drive_letter='X', auto_mount=True)
        mount2 = Mount(remote_name='fail', remote_path='', drive_letter='Y', auto_mount=True)
        type(mount1).is_mounted = PropertyMock(return_value=False)
        type(mount2).is_mounted = PropertyMock(return_value=False)
        manager.mounts['ok'] = mount1
        manager.mounts['fail'] = mount2

        def mock_mount(name):
            return name == 'ok'

        mocker.patch.object(manager, 'mount', side_effect=mock_mount)
        manager.auto_mount_all()

    def test_auto_mount_all_exception(self, manager, mocker):
        from app.models.mount import Mount
        mount = Mount(remote_name='err', remote_path='', drive_letter='X', auto_mount=True)
        type(mount).is_mounted = PropertyMock(return_value=False)
        manager.mounts['err'] = mount

        mocker.patch.object(manager, 'mount', side_effect=Exception("mount error"))
        manager.auto_mount_all()


    def test_mount_starts_worker(self, manager, mocker):
        from app.models.mount import Mount, MountStatus
        mount = Mount(remote_name='test', remote_path='', drive_letter='X')
        mount.status = MountStatus.UNMOUNTED
        manager.mounts['test'] = mount

        mock_worker_cls = mocker.patch('app.core.mount_manager.MountWorker')
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        result = manager.mount('test')

        assert result is True
        assert mount.status == MountStatus.MOUNTING
        mock_worker.start.assert_called_once()


class TestMountWorkerDeep:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = 'rclone.exe'
        rclone.config_path = 'config.conf'
        return rclone

    @pytest.fixture
    def mount(self):
        from app.models.mount import Mount
        return Mount(remote_name='test', remote_path='/docs', drive_letter='X',
                     cache_mode='full', vfs_cache_max_size='5G')

    def test_run_invalid_config_no_remote(self, mock_rclone):
        from app.core.mount_manager import MountWorker
        from app.models.mount import Mount
        mount = Mount(remote_name='x', remote_path='', drive_letter='X')
        object.__setattr__(mount, 'remote_name', '')
        worker = MountWorker(mock_rclone, mount)

        finished = MagicMock()
        worker.finished.connect(finished)
        worker.run()

        finished.assert_called_once()
        assert finished.call_args[0][1] is False

    def test_run_with_read_only(self, mock_rclone, mount, mocker):
        from app.core.mount_manager import MountWorker
        mount.read_only = True

        worker = MountWorker(mock_rclone, mount)
        mock_process = MagicMock()
        mock_process.pid = 100

        with patch('subprocess.Popen', return_value=mock_process) as mock_popen:
            with patch('app.core.mount_manager.get_cache_dir', return_value=''):
                worker.run()
                call_args = mock_popen.call_args[0][0]
                assert '--read-only' in call_args

    def test_run_with_cache_dir(self, mock_rclone, mount, mocker):
        from app.core.mount_manager import MountWorker

        worker = MountWorker(mock_rclone, mount)
        mock_process = MagicMock()
        mock_process.pid = 100

        with patch('subprocess.Popen', return_value=mock_process):
            with patch('app.core.mount_manager.get_cache_dir', return_value='C:\\cache'):
                worker.run()

    def test_run_exception_with_stderr(self, mock_rclone, mount, mocker):
        from app.core.mount_manager import MountWorker

        worker = MountWorker(mock_rclone, mount)
        finished = MagicMock()
        worker.finished.connect(finished)

        mock_stderr = MagicMock()
        mock_stderr.name = 'temp.log'
        mock_stderr.read.return_value = 'detailed error info'

        with patch('subprocess.Popen', side_effect=Exception("popen failed")):
            with patch('tempfile.NamedTemporaryFile', return_value=mock_stderr):
                with patch('app.core.mount_manager.get_cache_dir', return_value=''):
                    worker.run()

        assert finished.call_args[0][1] is False

    def test_stop_timeout_then_kill(self, mock_rclone, mount):
        from app.core.mount_manager import MountWorker
        worker = MountWorker(mock_rclone, mount)
        mock_process = MagicMock()
        mock_process.wait.side_effect = [subprocess.TimeoutExpired('cmd', 5), None]
        worker.process = mock_process

        worker.stop()

        mock_process.kill.assert_called_once()
        assert worker.process is None

    def test_stop_process_already_dead(self, mock_rclone, mount):
        from app.core.mount_manager import MountWorker
        worker = MountWorker(mock_rclone, mount)
        mock_process = MagicMock()
        mock_process.terminate.side_effect = ProcessLookupError()
        worker.process = mock_process

        worker.stop()

        assert worker.process is None
