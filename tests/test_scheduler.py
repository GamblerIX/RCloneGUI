import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call


class TestSchedulerThread:

    def test_init(self, qtbot):
        from app.core.scheduler import SchedulerThread

        thread = SchedulerThread()
        assert thread._timer.interval() == 60000
        assert thread._last_minute == -1

    def test_start(self, qtbot):
        from app.core.scheduler import SchedulerThread

        thread = SchedulerThread()

        with patch.object(thread._timer, 'isActive', return_value=False):
            with patch.object(thread._timer, 'start') as mock_start:
                with patch.object(thread, 'tick') as mock_tick:
                    thread.start()
                    mock_start.assert_called_once()

    def test_stop(self, qtbot):
        from app.core.scheduler import SchedulerThread

        thread = SchedulerThread()

        with patch.object(thread._timer, 'stop') as mock_stop:
            thread.stop()
            mock_stop.assert_called_once()


class TestSyncScheduler:

    @pytest.fixture
    def scheduler(self, qtbot):
        from app.core.scheduler import SyncScheduler
        return SyncScheduler()

    def test_init(self, scheduler):
        assert scheduler._scheduled_tasks == {}
        assert scheduler._last_run_times == {}
        assert scheduler._triggered_tasks == set()
        assert scheduler._scheduler_thread is None
        assert scheduler._check_callback is None

    def test_set_check_callback(self, scheduler):
        callback = MagicMock()
        scheduler.set_check_callback(callback)
        assert scheduler._check_callback == callback

    def test_start(self, scheduler):
        with patch('app.core.scheduler.SchedulerThread') as mock_thread_class:
            mock_thread = MagicMock()
            mock_thread_class.return_value = mock_thread
            mock_thread._timer.isActive.return_value = False

            scheduler.start()

            assert scheduler._scheduler_thread is not None
            mock_thread.start.assert_called_once()

    def test_stop(self, scheduler):
        with patch('app.core.scheduler.SchedulerThread') as mock_thread_class:
            mock_thread = MagicMock()
            mock_thread_class.return_value = mock_thread

            scheduler.start()
            scheduler.stop()

            mock_thread.stop.assert_called_once()

    def test_add_task_success(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter') as mock_croniter:
                result = scheduler.add_task('task1', '0 2 * * *')
                assert result is True
                assert 'task1' in scheduler._scheduled_tasks
                assert scheduler._scheduled_tasks['task1'] == '0 2 * * *'

    def test_add_task_no_croniter(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', False):
            result = scheduler.add_task('task1', '0 2 * * *')
            assert result is False

    def test_add_task_invalid_cron(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=ValueError('Invalid')):
                result = scheduler.add_task('task1', 'invalid')
                assert result is False

    def test_remove_task(self, scheduler):
        scheduler._scheduled_tasks['task1'] = '0 2 * * *'
        scheduler._last_run_times['task1'] = datetime.now()
        scheduler._triggered_tasks.add('task1')

        scheduler.remove_task('task1')

        assert 'task1' not in scheduler._scheduled_tasks
        assert 'task1' not in scheduler._last_run_times
        assert 'task1' not in scheduler._triggered_tasks

    def test_update_task(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter'):
                scheduler._scheduled_tasks['task1'] = '0 2 * * *'
                scheduler._last_run_times['task1'] = datetime.now()

                result = scheduler.update_task('task1', '0 3 * * *')

                assert result is True
                assert scheduler._scheduled_tasks['task1'] == '0 3 * * *'

    def test_update_task_not_exists(self, scheduler):
        result = scheduler.update_task('task1', '0 3 * * *')
        assert result is False

    def test_update_last_run(self, scheduler):
        scheduler._scheduled_tasks['task1'] = '0 2 * * *'
        scheduler._triggered_tasks.add('task1')

        test_time = datetime(2024, 1, 1, 12, 0, 0)
        scheduler.update_last_run('task1', test_time)

        assert scheduler._last_run_times['task1'] == test_time
        assert 'task1' not in scheduler._triggered_tasks

    def test_get_next_run(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            mock_itr = MagicMock()
            mock_itr.get_next.return_value = datetime(2024, 1, 2, 2, 0, 0)

            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                scheduler._scheduled_tasks['task1'] = '0 2 * * *'

                next_run = scheduler.get_next_run('task1')

                assert next_run is not None

    def test_get_next_run_no_croniter(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', False):
            result = scheduler.get_next_run('task1')
            assert result is None

    def test_get_next_run_task_not_exists(self, scheduler):
        result = scheduler.get_next_run('task1')
        assert result is None

    def test_get_next_run_text(self, scheduler):
        with patch.object(scheduler, 'get_next_run', return_value=datetime(2024, 1, 1, 12, 0, 0)):
            result = scheduler.get_next_run_text('task1')
            assert '2024-01-01 12:00' in result

    def test_get_next_run_text_not_set(self, scheduler):
        with patch.object(scheduler, 'get_next_run', return_value=None):
            result = scheduler.get_next_run_text('task1')
            assert result == "未设置"

    def test_is_scheduled(self, scheduler):
        assert scheduler.is_scheduled('task1') is False

        scheduler._scheduled_tasks['task1'] = '0 2 * * *'
        assert scheduler.is_scheduled('task1') is True

    def test_validate_cron_success(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter'):
                result = scheduler.validate_cron('0 2 * * *')
                assert result is True

    def test_validate_cron_no_croniter(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', False):
            result = scheduler.validate_cron('0 2 * * *')
            assert result is False

    def test_validate_cron_invalid(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=ValueError()):
                result = scheduler.validate_cron('invalid')
                assert result is False

    def test_validate_cron_empty(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            result = scheduler.validate_cron('')
            assert result is False

    def test_get_cron_description(self, scheduler):
        assert scheduler.get_cron_description('0 0 * * *') == "每天午夜"
        assert scheduler.get_cron_description('0 2 * * *') == "每天凌晨 2 点"
        assert scheduler.get_cron_description('0 */6 * * *') == "每 6 小时"
        assert scheduler.get_cron_description('*/5 * * * *') == "每 5 分钟"

    def test_get_cron_description_unknown(self, scheduler):
        assert scheduler.get_cron_description('1 2 3 4 5') == "1 2 3 4 5"

    def test_clear(self, scheduler):
        scheduler._scheduled_tasks['task1'] = '0 2 * * *'
        scheduler._last_run_times['task1'] = datetime.now()
        scheduler._triggered_tasks.add('task1')
        scheduler._last_check_time = datetime.now()

        scheduler.clear()

        assert scheduler._scheduled_tasks == {}
        assert scheduler._last_run_times == {}
        assert scheduler._triggered_tasks == set()
        assert scheduler._last_check_time is None

    def test_get_all_scheduled_tasks(self, scheduler):
        scheduler._scheduled_tasks['task1'] = '0 2 * * *'
        scheduler._scheduled_tasks['task2'] = '0 3 * * *'

        result = scheduler.get_all_scheduled_tasks()

        assert result == {'task1': '0 2 * * *', 'task2': '0 3 * * *'}

    def test_on_tick_no_croniter(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', False):
            scheduler._on_tick()

    def test_on_tick_task_due(self, scheduler, qtbot):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            mock_itr = MagicMock()
            mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=1)

            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                scheduler._scheduled_tasks['task1'] = '0 2 * * *'

                with qtbot.waitSignal(scheduler.taskDue, timeout=1000):
                    scheduler._on_tick()

    def test_on_tick_time_rewind(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            scheduler._last_check_time = datetime.now() + timedelta(hours=1)
            scheduler._triggered_tasks.add('task1')

            scheduler._on_tick()

            assert scheduler._triggered_tasks == set()

    def test_on_tick_callback_error(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            mock_itr = MagicMock()
            mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=1)

            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                scheduler._scheduled_tasks['task1'] = '0 2 * * *'
                scheduler._check_callback = MagicMock(side_effect=Exception('Callback error'))

                scheduler._on_tick()

    def test_on_tick_invalid_cron(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=ValueError('Invalid')):
                scheduler._scheduled_tasks['task1'] = 'invalid'

                scheduler._on_tick()
