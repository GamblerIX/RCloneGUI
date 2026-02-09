import pytest
import subprocess
from unittest.mock import MagicMock, patch, call


class TestSyncWorkerDeep:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone
        rclone = MagicMock(spec=RClone)
        rclone.rclone_path = '/usr/bin/rclone'
        rclone.config_path = '/tmp/rclone.conf'
        return rclone

    @pytest.fixture
    def sync_task(self):
        from app.models.sync_task import SyncTask, SyncMode
        return SyncTask(
            id='test-task',
            name='Test Sync',
            source='remote:src',
            destination='/dst',
            mode=SyncMode.SYNC,
        )

    @pytest.fixture
    def worker(self, mock_rclone, sync_task):
        from app.core.sync_manager import SyncWorker
        return SyncWorker(mock_rclone, sync_task)


    def test_parse_progress_with_percentage_and_bytes(self, worker, mocker):
        progress_spy = mocker.MagicMock()
        worker.progress.connect(progress_spy)
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "50.0 MiB / 100.0 MiB, 50%, 10.0 MiB/s, ETA 5s"
        worker._parse_progress(line)

        progress_spy.assert_called_once()
        args = progress_spy.call_args[0]
        assert args[0] == 'test-task'
        assert args[1] == 50
        assert args[3] == int(50.0 * 1024**2)

        stats_spy.assert_called_once()
        stats = stats_spy.call_args[0][1]
        assert stats['percentage'] == 50
        assert stats['bytes_transferred'] == int(50.0 * 1024**2)
        assert stats['bytes_total'] == int(100.0 * 1024**2)

    def test_parse_progress_with_kib_units(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "512.0 KiB / 1024.0 KiB, 50%"
        worker._parse_progress(line)

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == int(512.0 * 1024)
        assert stats['bytes_total'] == int(1024.0 * 1024)

    def test_parse_progress_with_gib_units(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "1.5 GiB / 3.0 GiB, 50%"
        worker._parse_progress(line)

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == int(1.5 * 1024**3)
        assert stats['bytes_total'] == int(3.0 * 1024**3)

    def test_parse_progress_with_tib_units(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)
        progress_spy = mocker.MagicMock()
        worker.progress.connect(progress_spy)
        line = "0.001 TiB / 0.002 TiB, 50%"
        worker._parse_progress(line)

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == int(0.001 * 1024**4)
        assert stats['bytes_total'] == int(0.002 * 1024**4)

    def test_parse_progress_with_bytes_units(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "500.0 B / 1000.0 B, 50%"
        worker._parse_progress(line)

        stats = stats_spy.call_args[0][1]
        assert stats['bytes_transferred'] == 500
        assert stats['bytes_total'] == 1000

    def test_parse_progress_with_files(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "Transferred: 10/100"
        worker._parse_progress(line)

        stats_spy.assert_called_once()
        stats = stats_spy.call_args[0][1]
        assert stats['files_transferred'] == 10
        assert stats['files_total'] == 100

    def test_parse_progress_with_speed(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "50.0 MiB / 100.0 MiB, 50%, 10.5 MiB/s, ETA 5s"
        worker._parse_progress(line)

        stats = stats_spy.call_args[0][1]
        assert stats['speed'] == int(10.5 * 1024**2)

    def test_parse_progress_with_eta(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "50.0 MiB / 100.0 MiB, 50%, 10.0 MiB/s, ETA 1m30s"
        worker._parse_progress(line)

        stats = stats_spy.call_args[0][1]
        assert stats['eta'] == '1m30s'

    def test_parse_progress_empty_line(self, worker, mocker):
        progress_spy = mocker.MagicMock()
        worker.progress.connect(progress_spy)
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker._parse_progress("")

        progress_spy.assert_not_called()
        stats_spy.assert_not_called()

    def test_parse_progress_unmatched_line(self, worker, mocker):
        progress_spy = mocker.MagicMock()
        worker.progress.connect(progress_spy)
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker._parse_progress("Some random log output that doesn't match")

        progress_spy.assert_not_called()
        stats_spy.assert_not_called()

    def test_parse_progress_speed_kib(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "50.0 MiB / 100.0 MiB, 50%, 512.0 KiB/s"
        worker._parse_progress(line)

        stats = stats_spy.call_args[0][1]
        assert stats['speed'] == int(512.0 * 1024)

    def test_parse_progress_speed_gib(self, worker, mocker):
        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        line = "50.0 MiB / 100.0 MiB, 50%, 1.0 GiB/s"
        worker._parse_progress(line)

        stats = stats_spy.call_args[0][1]
        assert stats['speed'] == int(1.0 * 1024**3)


    def test_cancel_normal_termination(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.wait.return_value = None
        mock_process.communicate.return_value = ('', '')
        worker._process = mock_process

        worker.cancel()

        assert worker._cancelled is True
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)
        mock_process.communicate.assert_called_once()
        assert worker._process is None

    def test_cancel_timeout_force_kill(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired('cmd', 5),
            None,
        ]
        mock_process.communicate.return_value = ('', '')
        worker._process = mock_process

        worker.cancel()

        assert worker._cancelled is True
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        assert worker._process is None

    def test_cancel_process_already_dead(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.terminate.side_effect = ProcessLookupError("No such process")
        worker._process = mock_process

        worker.cancel()

        assert worker._cancelled is True
        assert worker._process is None

    def test_cancel_permission_error(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.terminate.side_effect = PermissionError("Permission denied")
        worker._process = mock_process

        worker.cancel()

        assert worker._cancelled is True
        assert worker._process is None

    def test_cancel_no_process(self, worker):
        worker._process = None

        worker.cancel()

        assert worker._cancelled is True
        assert worker._process is None

    def test_cancel_unexpected_error(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.terminate.side_effect = RuntimeError("Unexpected")
        worker._process = mock_process

        worker.cancel()

        assert worker._cancelled is True
        assert worker._process is None


    def test_run_bisync_mode(self, worker, mocker):
        from app.models.sync_task import SyncMode
        worker.task.mode = SyncMode.BISYNC

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        started_spy = mocker.MagicMock()
        finished_spy = mocker.MagicMock()
        worker.started.connect(started_spy)
        worker.finished.connect(finished_spy)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert 'bisync' in cmd
        assert worker.task.source in cmd
        assert worker.task.destination in cmd

    def test_run_cancelled_during_execution(self, worker, mocker):
        mock_process = MagicMock()
        call_count = [0]

        def readline_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                worker._cancelled = True
                return "some output\n"
            return ''

        mock_process.stderr.readline.side_effect = readline_side_effect
        mock_process.wait.return_value = 0
        mocker.patch('subprocess.Popen', return_value=mock_process)

        finished_spy = mocker.MagicMock()
        worker.finished.connect(finished_spy)

        worker.run()

        mock_process.terminate.assert_called_once()
        finished_spy.assert_called_once()
        args = finished_spy.call_args[0]
        assert args[0] == 'test-task'
        assert args[1] is False
        assert '取消' in args[2]

    def test_run_exception_during_execution(self, worker, mocker):
        mocker.patch('subprocess.Popen', side_effect=OSError("Command not found"))

        finished_spy = mocker.MagicMock()
        worker.finished.connect(finished_spy)

        worker.run()

        finished_spy.assert_called_once()
        args = finished_spy.call_args[0]
        assert args[0] == 'test-task'
        assert args[1] is False
        assert 'Command not found' in args[2]

    def test_run_with_bandwidth_limit(self, worker, mocker):
        worker.task.bandwidth_limit = '10M'

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert '--bwlimit' in cmd
        assert '10M' in cmd

    def test_run_with_dry_run(self, worker, mocker):
        worker.task.dry_run = True

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert '--dry-run' in cmd

    def test_run_with_delete_excluded(self, worker, mocker):
        worker.task.delete_excluded = True

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert '--delete-excluded' in cmd

    def test_run_with_exclude_patterns(self, worker, mocker):
        worker.task.exclude_patterns = ['*.tmp', '*.log']

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        exclude_indices = [i for i, x in enumerate(cmd) if x == '--exclude']
        assert len(exclude_indices) == 2
        assert cmd[exclude_indices[0] + 1] == '*.tmp'
        assert cmd[exclude_indices[1] + 1] == '*.log'

    def test_run_with_all_options(self, worker, mocker):
        worker.task.bandwidth_limit = '5M'
        worker.task.dry_run = True
        worker.task.delete_excluded = True
        worker.task.exclude_patterns = ['*.bak']

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert '--bwlimit' in cmd
        assert '5M' in cmd
        assert '--dry-run' in cmd
        assert '--delete-excluded' in cmd
        assert '--exclude' in cmd
        assert '*.bak' in cmd

    def test_run_without_optional_flags(self, worker, mocker):
        worker.task.bandwidth_limit = ''
        worker.task.dry_run = False
        worker.task.delete_excluded = False
        worker.task.exclude_patterns = []

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert '--bwlimit' not in cmd
        assert '--dry-run' not in cmd
        assert '--delete-excluded' not in cmd
        assert '--exclude' not in cmd

    def test_run_with_config_path(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert '--config' in cmd
        assert '/tmp/rclone.conf' in cmd

    def test_run_without_config_path(self, worker, mocker):
        worker.rclone.config_path = None

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert '--config' not in cmd

    def test_run_sync_mode(self, worker, mocker):
        from app.models.sync_task import SyncMode
        worker.task.mode = SyncMode.SYNC

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert 'sync' in cmd

    def test_run_copy_mode(self, worker, mocker):
        from app.models.sync_task import SyncMode
        worker.task.mode = SyncMode.COPY

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert 'copy' in cmd

    def test_run_move_mode(self, worker, mocker):
        from app.models.sync_task import SyncMode
        worker.task.mode = SyncMode.MOVE

        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mock_popen = mocker.patch('subprocess.Popen', return_value=mock_process)

        worker.run()

        cmd = mock_popen.call_args[0][0]
        assert 'move' in cmd

    def test_run_failure_return_code(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 1
        mocker.patch('subprocess.Popen', return_value=mock_process)

        finished_spy = mocker.MagicMock()
        worker.finished.connect(finished_spy)

        worker.run()

        finished_spy.assert_called_once()
        args = finished_spy.call_args[0]
        assert args[1] is False
        assert '1' in args[2]

    def test_run_reads_progress_lines(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.stderr.readline.side_effect = [
            "50.0 MiB / 100.0 MiB, 50%, 10.0 MiB/s, ETA 5s\n",
            "Transferred: 5/10\n",
            "",
        ]
        mock_process.wait.return_value = 0
        mocker.patch('subprocess.Popen', return_value=mock_process)

        stats_spy = mocker.MagicMock()
        worker.stats_update.connect(stats_spy)

        worker.run()

        assert stats_spy.call_count == 2

    def test_run_success_message(self, worker, mocker):
        mock_process = MagicMock()
        mock_process.stderr.readline.return_value = ''
        mock_process.wait.return_value = 0
        mocker.patch('subprocess.Popen', return_value=mock_process)

        finished_spy = mocker.MagicMock()
        worker.finished.connect(finished_spy)

        worker.run()

        finished_spy.assert_called_once()
        args = finished_spy.call_args[0]
        assert args[0] == 'test-task'
        assert args[1] is True
        assert args[2] == '完成'


class TestSyncManagerDeep:

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
        mgr._config_file = tmp_path / "config" / "sync_tasks.json"
        return mgr

    @pytest.fixture
    def task_in_manager(self, manager):
        from app.models.sync_task import SyncTask, SyncStatus
        task = SyncTask(
            id='task-1',
            name='Test Task',
            source='remote:src',
            destination='/dst',
        )
        task.status = SyncStatus.RUNNING
        manager.tasks['task-1'] = task
        return task


    def test_on_task_finished_success_updates_status_and_saves(self, manager, task_in_manager, mocker):
        from app.models.sync_task import SyncStatus
        task_in_manager.error_message = "old error"
        save_spy = mocker.patch.object(manager, 'save_tasks')

        manager._on_task_finished('task-1', True, '同步完成')

        assert task_in_manager.status == SyncStatus.COMPLETED
        assert task_in_manager.error_message is None
        assert task_in_manager.last_run is not None
        save_spy.assert_called_once()

    def test_on_task_finished_failure_sets_error_and_emits_signal(self, manager, task_in_manager, mocker):
        from app.models.sync_task import SyncStatus
        error_spy = mocker.MagicMock()
        manager.taskError.connect(error_spy)

        manager._on_task_finished('task-1', False, '同步失败: 连接超时')

        assert task_in_manager.status == SyncStatus.ERROR
        assert task_in_manager.error_message == '同步失败: 连接超时'
        error_spy.assert_called_once_with('task-1', '同步失败: 连接超时')

    def test_on_task_finished_emits_completed_signal(self, manager, task_in_manager, mocker):
        completed_spy = mocker.MagicMock()
        manager.taskCompleted.connect(completed_spy)

        manager._on_task_finished('task-1', True, '完成')

        completed_spy.assert_called_once_with('task-1', True, '完成')

    def test_on_task_finished_emits_status_changed_signal(self, manager, task_in_manager, mocker):
        from app.models.sync_task import SyncStatus
        status_spy = mocker.MagicMock()
        manager.taskStatusChanged.connect(status_spy)

        manager._on_task_finished('task-1', True, '完成')

        status_spy.assert_called_once_with('task-1', SyncStatus.COMPLETED)

    def test_on_task_finished_scheduled_task_updates_scheduler(self, manager, task_in_manager, mocker):
        task_in_manager.scheduled = True
        update_spy = mocker.patch.object(manager.scheduler, 'update_last_run')

        manager._on_task_finished('task-1', True, '完成')

        update_spy.assert_called_once_with('task-1', task_in_manager.last_run)

    def test_on_task_finished_non_scheduled_task_no_scheduler_update(self, manager, task_in_manager, mocker):
        task_in_manager.scheduled = False
        update_spy = mocker.patch.object(manager.scheduler, 'update_last_run')

        manager._on_task_finished('task-1', True, '完成')

        update_spy.assert_not_called()

    def test_on_task_finished_removes_worker(self, manager, task_in_manager, mocker):
        manager.workers['task-1'] = MagicMock()

        manager._on_task_finished('task-1', True, '完成')

        assert 'task-1' not in manager.workers

    def test_on_task_finished_exception_caught(self, manager, task_in_manager, mocker):
        mocker.patch.object(manager, 'save_tasks', side_effect=RuntimeError("DB error"))

        manager._on_task_finished('task-1', True, '完成')

    def test_on_task_finished_nonexistent_task(self, manager, mocker):
        manager._on_task_finished('nonexistent', True, '完成')


    def test_on_scheduled_task_due_emits_signal_and_runs_task(self, manager, task_in_manager, mocker):
        from app.models.sync_task import SyncStatus
        task_in_manager.status = SyncStatus.IDLE

        signal_spy = mocker.patch('app.core.sync_manager.signalBus')
        run_spy = mocker.patch.object(manager, 'run_task')

        manager._on_scheduled_task_due('task-1')

        signal_spy.scheduledTaskDue.emit.assert_called_once_with('task-1', 'Test Task')
        run_spy.assert_called_once_with('task-1')

    def test_on_scheduled_task_due_nonexistent_task(self, manager, mocker):
        signal_spy = mocker.patch('app.core.sync_manager.signalBus')
        run_spy = mocker.patch.object(manager, 'run_task')

        manager._on_scheduled_task_due('nonexistent')

        signal_spy.scheduledTaskDue.emit.assert_not_called()
        run_spy.assert_not_called()

    def test_on_scheduled_task_due_exception_caught(self, manager, task_in_manager, mocker):
        mocker.patch('app.core.sync_manager.signalBus')
        mocker.patch.object(manager, 'run_task', side_effect=RuntimeError("Unexpected"))

        manager._on_scheduled_task_due('task-1')


    def test_on_task_stats_update_forwards_signal(self, manager, mocker):
        stats_spy = mocker.MagicMock()
        manager.taskStatsUpdate.connect(stats_spy)

        test_stats = {'percentage': 50, 'speed': 1024, 'eta': '5s'}
        manager._on_task_stats_update('task-1', test_stats)

        stats_spy.assert_called_once_with('task-1', test_stats)

    def test_on_task_stats_update_empty_stats(self, manager, mocker):
        stats_spy = mocker.MagicMock()
        manager.taskStatsUpdate.connect(stats_spy)

        manager._on_task_stats_update('task-1', {})

        stats_spy.assert_called_once_with('task-1', {})


    def test_cancel_task_no_worker_resets_status(self, manager, task_in_manager, mocker):
        from app.models.sync_task import SyncStatus
        task_in_manager.status = SyncStatus.RUNNING
        assert 'task-1' not in manager.workers

        status_spy = mocker.MagicMock()
        manager.taskStatusChanged.connect(status_spy)

        manager.cancel_task('task-1')

        assert task_in_manager.status == SyncStatus.IDLE
        status_spy.assert_called_once_with('task-1', SyncStatus.IDLE)

    def test_cancel_task_nonexistent_task_no_crash(self, manager):
        manager.cancel_task('nonexistent')


    def test_load_tasks_invalid_data_skipped(self, manager, tmp_path):
        import json
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "sync_tasks.json"
        manager._config_file = config_file

        data = [
            {
                'id': 'valid-1',
                'name': 'Valid Task',
                'source': 'remote:src',
                'destination': '/dst',
                'mode': 'sync',
                'status': 'idle',
            },
            {
                'id': 'invalid-1',
                'name': 'Invalid Task',
                'source': 'remote:src',
                'destination': '/dst',
                'mode': 'invalid_mode',
            },
            {
                'id': 'valid-2',
                'name': 'Valid Task 2',
                'source': 'remote:src2',
                'destination': '/dst2',
                'mode': 'copy',
                'status': 'idle',
            },
        ]
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        result = manager.load_tasks()

        assert result is True
        assert len(manager.tasks) == 2
        assert 'valid-1' in manager.tasks
        assert 'valid-2' in manager.tasks
        assert 'invalid-1' not in manager.tasks

    def test_load_tasks_general_exception_returns_false(self, manager, tmp_path, mocker):
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "sync_tasks.json"
        manager._config_file = config_file

        config_file.write_text('[]')

        mocker.patch('builtins.open', side_effect=PermissionError("Permission denied"))

        result = manager.load_tasks()

        assert result is False

    def test_load_tasks_all_invalid_data(self, manager, tmp_path):
        import json
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "sync_tasks.json"
        manager._config_file = config_file

        data = [
            {'id': 'bad-1', 'mode': 'invalid_mode'},
            {'id': 'bad-2', 'mode': 'another_invalid'},
        ]
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        result = manager.load_tasks()

        assert result is True
        assert len(manager.tasks) == 0

    def test_load_tasks_json_decode_error(self, manager, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "sync_tasks.json"
        manager._config_file = config_file

        config_file.write_text('not valid json {{{')

        result = manager.load_tasks()

        assert result is False


    def test_save_tasks_exception_caught(self, manager, mocker):
        mocker.patch('builtins.open', side_effect=PermissionError("Permission denied"))
        log_spy = mocker.patch('app.core.sync_manager.logger')

        manager.save_tasks()

        log_spy.error.assert_called_once()
        assert '保存同步任务失败' in log_spy.error.call_args[0][0]

    def test_save_tasks_with_tasks(self, manager, task_in_manager, tmp_path):
        import json
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "sync_tasks.json"
        manager._config_file = config_file

        manager.save_tasks()

        assert config_file.exists()
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]['id'] == 'task-1'


    def test_shutdown_cancels_all_workers_and_stops_scheduler(self, manager, mocker):
        from app.models.sync_task import SyncTask, SyncStatus

        for i in range(3):
            task_id = f'task-{i}'
            task = SyncTask(
                id=task_id,
                name=f'Task {i}',
                source=f'remote:src{i}',
                destination=f'/dst{i}',
            )
            task.status = SyncStatus.RUNNING
            manager.tasks[task_id] = task
            manager.workers[task_id] = MagicMock()

        cancel_spy = mocker.patch.object(manager, 'cancel_task', wraps=manager.cancel_task)
        stop_spy = mocker.patch.object(manager.scheduler, 'stop')

        manager.shutdown()

        assert cancel_spy.call_count == 3
        called_ids = {c[0][0] for c in cancel_spy.call_args_list}
        assert called_ids == {'task-0', 'task-1', 'task-2'}

        stop_spy.assert_called_once()

    def test_shutdown_no_workers(self, manager, mocker):
        stop_spy = mocker.patch.object(manager.scheduler, 'stop')

        manager.shutdown()

        stop_spy.assert_called_once()

    def test_shutdown_clears_workers(self, manager, task_in_manager, mocker):
        worker_mock = MagicMock()
        manager.workers['task-1'] = worker_mock
        mocker.patch.object(manager.scheduler, 'stop')

        manager.shutdown()

        assert 'task-1' not in manager.workers
        worker_mock.cancel.assert_called_once()
