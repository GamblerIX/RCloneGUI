import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestSyncManager:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone, RCloneResult
        rclone = MagicMock(spec=RClone)
        rclone.sync.return_value = RCloneResult(True, '', '', 0)
        rclone.copy.return_value = RCloneResult(True, '', '', 0)
        rclone.move.return_value = RCloneResult(True, '', '', 0)
        return rclone

    @pytest.fixture
    def sync_manager(self, mock_rclone, tmp_path, mocker):
        from app.core.sync_manager import SyncManager
        mocker.patch('app.core.sync_manager.APP_PATH', tmp_path)
        manager = SyncManager(mock_rclone)
        manager._config_file = tmp_path / "config" / "sync_tasks.json"
        return manager

    def test_init(self, sync_manager):
        assert sync_manager.tasks == {}
        assert sync_manager.workers == {}

    def test_load_tasks_no_file(self, sync_manager):
        sync_manager.load_tasks()
        assert sync_manager.tasks == {}

    def test_load_tasks_with_file(self, sync_manager):
        sync_manager._config_file.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {'id': 'task1', 'name': 'Test 1', 'source': '/src', 'destination': 'remote:/dst', 'mode': 'sync'},
            {'id': 'task2', 'name': 'Test 2', 'source': '/data', 'destination': 'remote:/backup', 'mode': 'copy'}
        ]
        with open(sync_manager._config_file, 'w') as f:
            json.dump(data, f)

        sync_manager.load_tasks()

        assert len(sync_manager.tasks) == 2
        assert 'task1' in sync_manager.tasks
        assert 'task2' in sync_manager.tasks

    def test_load_tasks_invalid_json(self, sync_manager):
        sync_manager._config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager._config_file, 'w') as f:
            f.write('not valid json')

        sync_manager.load_tasks()
        assert sync_manager.tasks == {}

    def test_save_tasks(self, sync_manager):
        from app.models.sync_task import SyncTask
        sync_manager.tasks['test'] = SyncTask(
            id='test',
            name='Test Task',
            source='/local',
            destination='remote:/backup'
        )

        sync_manager.save_tasks()

        assert sync_manager._config_file.exists()
        with open(sync_manager._config_file, 'r') as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]['id'] == 'test'

    def test_add_task(self, sync_manager):
        from app.models.sync_task import SyncMode

        task = sync_manager.add_task(
            name='New Task',
            source='/source',
            destination='remote:/dest',
            mode=SyncMode.COPY
        )

        assert task.name == 'New Task'
        assert task.source == '/source'
        assert task.destination == 'remote:/dest'
        assert task.mode == SyncMode.COPY
        assert task.id in sync_manager.tasks

    def test_remove_task(self, sync_manager):
        from app.models.sync_task import SyncTask
        sync_manager.tasks['test'] = SyncTask(
            id='test', name='Test', source='/src', destination='/dst'
        )

        sync_manager.remove_task('test')

        assert 'test' not in sync_manager.tasks

    def test_remove_task_cancels_if_running(self, sync_manager, mocker):
        from app.models.sync_task import SyncTask
        sync_manager.tasks['test'] = SyncTask(
            id='test', name='Test', source='/src', destination='/dst'
        )
        worker_mock = MagicMock()
        sync_manager.workers['test'] = worker_mock

        sync_manager.remove_task('test')

        worker_mock.cancel.assert_called_once()

    def test_run_task_not_found(self, sync_manager):
        result = sync_manager.run_task('nonexistent')
        assert result is False

    def test_run_task_already_running(self, sync_manager):
        from app.models.sync_task import SyncTask, SyncStatus
        task = SyncTask(id='test', name='Test', source='/src', destination='/dst')
        task.status = SyncStatus.RUNNING
        sync_manager.tasks['test'] = task

        result = sync_manager.run_task('test')

        assert result is False

    def test_cancel_task(self, sync_manager):
        from app.models.sync_task import SyncTask, SyncStatus
        sync_manager.tasks['test'] = SyncTask(
            id='test', name='Test', source='/src', destination='/dst'
        )
        worker_mock = MagicMock()
        sync_manager.workers['test'] = worker_mock

        sync_manager.cancel_task('test')

        worker_mock.cancel.assert_called_once()
        assert 'test' not in sync_manager.workers
        assert sync_manager.tasks['test'].status == SyncStatus.IDLE

    def test_on_task_started(self, sync_manager):
        from app.models.sync_task import SyncTask, SyncStatus
        sync_manager.tasks['test'] = SyncTask(
            id='test', name='Test', source='/src', destination='/dst'
        )

        sync_manager._on_task_started('test')

        assert sync_manager.tasks['test'].status == SyncStatus.RUNNING

    def test_on_task_progress(self, sync_manager):
        from app.models.sync_task import SyncTask
        sync_manager.tasks['test'] = SyncTask(
            id='test', name='Test', source='/src', destination='/dst'
        )

        sync_manager._on_task_progress('test', 50, 10, 1024)

        assert sync_manager.tasks['test'].progress == 50
        assert sync_manager.tasks['test'].files_transferred == 10
        assert sync_manager.tasks['test'].bytes_transferred == 1024

    def test_on_task_finished_success(self, sync_manager):
        from app.models.sync_task import SyncTask, SyncStatus
        sync_manager.tasks['test'] = SyncTask(
            id='test', name='Test', source='/src', destination='/dst'
        )
        sync_manager.workers['test'] = MagicMock()

        sync_manager._on_task_finished('test', True, 'Completed')

        assert sync_manager.tasks['test'].status == SyncStatus.COMPLETED
        assert sync_manager.tasks['test'].error_message is None
        assert sync_manager.tasks['test'].last_run is not None
        assert 'test' not in sync_manager.workers

    def test_on_task_finished_failure(self, sync_manager):
        from app.models.sync_task import SyncTask, SyncStatus
        sync_manager.tasks['test'] = SyncTask(
            id='test', name='Test', source='/src', destination='/dst'
        )
        sync_manager.workers['test'] = MagicMock()

        sync_manager._on_task_finished('test', False, 'Error occurred')

        assert sync_manager.tasks['test'].status == SyncStatus.ERROR
        assert sync_manager.tasks['test'].error_message == 'Error occurred'


class TestSyncWorker:

    @pytest.fixture
    def mock_rclone(self):
        from app.core.rclone import RClone, RCloneResult
        rclone = MagicMock(spec=RClone)
        rclone.sync.return_value = RCloneResult(True, '', '', 0)
        rclone.copy.return_value = RCloneResult(True, '', '', 0)
        rclone.move.return_value = RCloneResult(True, '', '', 0)
        return rclone

    @pytest.fixture
    def sync_task(self):
        from app.models.sync_task import SyncTask, SyncMode
        return SyncTask(
            id='test',
            name='Test Sync',
            source='/local/data',
            destination='remote:/backup',
            mode=SyncMode.SYNC
        )

    def test_worker_creation(self, mock_rclone, sync_task):
        from app.core.sync_manager import SyncWorker
        worker = SyncWorker(mock_rclone, sync_task)

        assert worker.rclone == mock_rclone
        assert worker.task == sync_task
        assert worker._cancelled is False

    def test_worker_cancel(self, mock_rclone, sync_task):
        from app.core.sync_manager import SyncWorker
        worker = SyncWorker(mock_rclone, sync_task)

        worker.cancel()

        assert worker._cancelled is True

    def test_worker_run_sync(self, mock_rclone, sync_task, mocker):
        from app.core.sync_manager import SyncWorker, SyncMode

        sync_task.mode = SyncMode.SYNC
        sync_task.bandwidth_limit = "10M"
        sync_task.dry_run = True
        sync_task.exclude_patterns = ["*.tmp"]

        mock_rclone.rclone_path = 'rclone'
        mock_rclone.config_path = None

        worker = SyncWorker(mock_rclone, sync_task)

        started = MagicMock()
        finished = MagicMock()
        worker.started.connect(started)
        worker.finished.connect(finished)

        mock_process = mocker.Mock()
        mock_process.poll.return_value = 0
        mock_process.wait.return_value = 0
        mock_process.stderr.readline.return_value = ''

        with patch('subprocess.Popen', return_value=mock_process) as mock_popen:
            worker.run()

            started.assert_called_with(sync_task.id)

            call_args = mock_popen.call_args[0][0]
            assert 'sync' in call_args
            assert '--bwlimit' in call_args
            assert '10M' in call_args
            assert '--dry-run' in call_args
            assert '--exclude' in call_args

            finished.assert_called_with(sync_task.id, True, "完成")

    def test_worker_run_copy(self, mock_rclone, sync_task, mocker):
        from app.core.sync_manager import SyncWorker, SyncMode
        sync_task.mode = SyncMode.COPY

        mock_rclone.rclone_path = 'rclone'
        mock_rclone.config_path = None

        worker = SyncWorker(mock_rclone, sync_task)

        mock_process = mocker.Mock()
        mock_process.poll.return_value = 0
        mock_process.wait.return_value = 0
        mock_process.stderr.readline.return_value = ''

        with patch('subprocess.Popen', return_value=mock_process) as mock_popen:
            worker.run()
            call_args = mock_popen.call_args[0][0]
            assert 'copy' in call_args

    def test_worker_run_move(self, mock_rclone, sync_task, mocker):
        from app.core.sync_manager import SyncWorker, SyncMode
        sync_task.mode = SyncMode.MOVE

        mock_rclone.rclone_path = 'rclone'
        mock_rclone.config_path = None

        worker = SyncWorker(mock_rclone, sync_task)

        mock_process = mocker.Mock()
        mock_process.poll.return_value = 0
        mock_process.wait.return_value = 0
        mock_process.stderr.readline.return_value = ''

        with patch('subprocess.Popen', return_value=mock_process) as mock_popen:
            worker.run()
            call_args = mock_popen.call_args[0][0]
            assert 'move' in call_args
