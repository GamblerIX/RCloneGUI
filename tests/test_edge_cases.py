import json
import logging
import signal
import subprocess
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest



class TestLoadTasksMixedData:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = '/usr/bin/rclone'
        rclone.config_path = '/tmp/rclone.conf'
        return rclone

    @pytest.fixture
    def manager(self, mock_rclone, tmp_path, mocker):
        from app.core.sync_manager import SyncManager
        mocker.patch('app.core.sync_manager.APP_PATH', tmp_path)
        mgr = SyncManager(mock_rclone)
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        mgr._config_file = config_dir / "sync_tasks.json"
        return mgr

    def test_valid_tasks_loaded_invalid_skipped(self, manager):
        data = [
            {
                'id': 'valid-1',
                'name': 'Valid Task 1',
                'source': 'remote:src',
                'destination': '/dst',
                'mode': 'sync',
                'status': 'idle',
            },
            {
                'id': 'invalid-1',
                'name': 'Invalid Mode Task',
                'source': 'remote:src',
                'destination': '/dst',
                'mode': 'nonexistent_mode',
            },
            {
                'id': 'valid-2',
                'name': 'Valid Task 2',
                'source': 'remote:src2',
                'destination': '/dst2',
                'mode': 'copy',
                'status': 'idle',
            },
            {
                'id': 'invalid-2',
                'name': 'Invalid Status Task',
                'source': 'remote:src',
                'destination': '/dst',
                'mode': 'sync',
                'status': 'nonexistent_status',
            },
        ]
        with open(manager._config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        result = manager.load_tasks()

        assert result is True
        assert len(manager.tasks) == 2
        assert 'valid-1' in manager.tasks
        assert 'valid-2' in manager.tasks
        assert 'invalid-1' not in manager.tasks
        assert 'invalid-2' not in manager.tasks

    def test_all_invalid_data_returns_true_empty_tasks(self, manager):
        data = [
            {'id': 'bad-1', 'mode': 'bad_mode'},
            {'id': 'bad-2', 'mode': 'another_bad'},
        ]
        with open(manager._config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        result = manager.load_tasks()

        assert result is True
        assert len(manager.tasks) == 0

    def test_single_valid_among_many_invalid(self, manager):
        data = [
            {'id': 'bad-1', 'mode': 'x'},
            {'id': 'bad-2', 'mode': 'y'},
            {
                'id': 'good-1',
                'name': 'Good',
                'source': 'r:s',
                'destination': '/d',
                'mode': 'move',
                'status': 'idle',
            },
            {'id': 'bad-3', 'mode': 'z'},
        ]
        with open(manager._config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        result = manager.load_tasks()

        assert result is True
        assert len(manager.tasks) == 1
        assert 'good-1' in manager.tasks



class TestTerminateProcessPlatformBranches:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = 'rclone'
        rclone.config_path = None
        return rclone

    @pytest.fixture
    def manager(self, mock_rclone, tmp_path, mocker):
        from app.core.mount_manager import MountManager
        mocker.patch('app.core.mount_manager.APP_PATH', tmp_path)
        mgr = MountManager(mock_rclone)
        mgr._config_file = tmp_path / "config" / "mounts.json"
        return mgr

    def test_windows_uses_taskkill(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_run = mocker.patch('subprocess.run')
        mocker.patch.object(manager, '_is_process_running', return_value=False)

        result = manager._terminate_process_gracefully(9999, timeout=1)

        assert result is True
        first_call_args = mock_run.call_args_list[0][0][0]
        assert 'taskkill' in first_call_args
        assert '/PID' in first_call_args
        assert '9999' in first_call_args

    def test_windows_force_kill_after_timeout(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_run = mocker.patch('subprocess.run')
        mocker.patch.object(manager, '_is_process_running', return_value=True)
        mocker.patch('time.sleep')

        result = manager._terminate_process_gracefully(9999, timeout=1)

        assert result is True
        force_calls = [
            c for c in mock_run.call_args_list
            if '/F' in c[0][0]
        ]
        assert len(force_calls) >= 1

    def test_posix_uses_sigterm(self, manager, mocker):
        mocker.patch('os.name', 'posix')
        mock_kill = mocker.patch('os.kill')
        mocker.patch.object(manager, '_is_process_running', return_value=False)

        result = manager._terminate_process_gracefully(9999, timeout=1)

        assert result is True
        mock_kill.assert_any_call(9999, signal.SIGTERM)

    def test_posix_force_kill_with_sigkill(self, manager, mocker):
        mocker.patch('os.name', 'posix')
        mock_kill = mocker.patch('os.kill')
        mocker.patch.object(manager, '_is_process_running', return_value=True)
        mocker.patch('time.sleep')

        SIGKILL_VALUE = 9
        had_sigkill = hasattr(signal, 'SIGKILL')
        if not had_sigkill:
            signal.SIGKILL = SIGKILL_VALUE

        try:
            result = manager._terminate_process_gracefully(9999, timeout=1)

            assert result is True
            sigkill_calls = [
                c for c in mock_kill.call_args_list
                if c[0][1] == SIGKILL_VALUE
            ]
            assert len(sigkill_calls) >= 1
        finally:
            if not had_sigkill:
                del signal.SIGKILL



class TestIsProcessRunningPlatformBranches:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = 'rclone'
        rclone.config_path = None
        return rclone

    @pytest.fixture
    def manager(self, mock_rclone, tmp_path, mocker):
        from app.core.mount_manager import MountManager
        mocker.patch('app.core.mount_manager.APP_PATH', tmp_path)
        mgr = MountManager(mock_rclone)
        return mgr

    def test_windows_running_process(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_result = MagicMock()
        mock_result.stdout.decode.return_value = 'Image Name  PID  12345  Services'
        mocker.patch('subprocess.run', return_value=mock_result)

        assert manager._is_process_running(12345) is True

    def test_windows_not_running_process(self, manager, mocker):
        mocker.patch('os.name', 'nt')
        mock_result = MagicMock()
        mock_result.stdout.decode.return_value = 'INFO: No tasks are running'
        mocker.patch('subprocess.run', return_value=mock_result)

        assert manager._is_process_running(12345) is False

    def test_posix_running_process(self, manager, mocker):
        mocker.patch('os.name', 'posix')
        mocker.patch('os.kill')

        assert manager._is_process_running(12345) is True

    def test_posix_not_running_process(self, manager, mocker):
        mocker.patch('os.name', 'posix')
        mocker.patch('os.kill', side_effect=ProcessLookupError())

        assert manager._is_process_running(12345) is False

    def test_posix_os_error_returns_false(self, manager, mocker):
        mocker.patch('os.name', 'posix')
        mocker.patch('os.kill', side_effect=OSError("Permission denied"))

        assert manager._is_process_running(12345) is False







class TestParseProgressUnitConversion:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = '/usr/bin/rclone'
        rclone.config_path = '/tmp/rclone.conf'
        return rclone

    @pytest.fixture
    def worker(self, mock_rclone):
        from app.core.sync_manager import SyncWorker
        from app.models.sync_task import SyncTask
        task = SyncTask(id='unit-test', name='Unit Test', source='r:s', destination='/d')
        return SyncWorker(mock_rclone, task)

    def test_bytes_unit_conversion(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker._parse_progress("100.0 B / 200.0 B, 50%")

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == 100
        assert stats['bytes_total'] == 200

    def test_kib_unit_conversion(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker._parse_progress("1.0 KiB / 2.0 KiB, 50%")

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == 1024
        assert stats['bytes_total'] == 2048

    def test_mib_unit_conversion(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker._parse_progress("1.0 MiB / 2.0 MiB, 50%")

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == 1024 ** 2
        assert stats['bytes_total'] == 2 * 1024 ** 2

    def test_gib_unit_conversion(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker._parse_progress("1.0 GiB / 2.0 GiB, 50%")

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == 1024 ** 3
        assert stats['bytes_total'] == 2 * 1024 ** 3

    def test_tib_unit_conversion(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker._parse_progress("0.001 TiB / 0.002 TiB, 50%")

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == int(0.001 * 1024 ** 4)
        assert stats['bytes_total'] == int(0.002 * 1024 ** 4)

    def test_mixed_units_transferred_and_total(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker._parse_progress("512.0 KiB / 1.0 MiB, 50%")

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == int(512.0 * 1024)
        assert stats['bytes_total'] == 1024 ** 2



class TestSchedulerNoDuplicateTrigger:

    @pytest.fixture
    def scheduler(self, qtbot):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            from app.core.scheduler import SyncScheduler
            s = SyncScheduler()
        return s

    def test_same_minute_no_duplicate_trigger(self, scheduler, qtbot):
        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=5)

        scheduler._scheduled_tasks = {'task-dup': '0 * * * *'}

        trigger_count = [0]

        def on_task_due(task_id):
            if task_id == 'task-dup':
                trigger_count[0] += 1

        scheduler.taskDue.connect(on_task_due)

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                scheduler._on_tick()
                scheduler._on_tick()
                scheduler._on_tick()

        assert trigger_count[0] == 1

    def test_triggered_tasks_set_prevents_duplicate(self, scheduler):
        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=5)

        scheduler._scheduled_tasks = {'task-a': '*/5 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                scheduler._on_tick()

        assert 'task-a' in scheduler._triggered_tasks

        signal_spy = MagicMock()
        scheduler.taskDue.connect(signal_spy)

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                scheduler._on_tick()

        signal_spy.assert_not_called()

    def test_different_tasks_both_trigger(self, scheduler, qtbot):
        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=5)

        scheduler._scheduled_tasks = {
            'task-x': '0 * * * *',
            'task-y': '0 * * * *',
        }

        triggered = []

        def on_task_due(task_id):
            triggered.append(task_id)

        scheduler.taskDue.connect(on_task_due)

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                scheduler._on_tick()

        assert 'task-x' in triggered
        assert 'task-y' in triggered
        assert len(triggered) == 2




