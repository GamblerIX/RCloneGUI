import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call


class TestSchedulerDeep:

    @pytest.fixture
    def scheduler(self, qtbot):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            from app.core.scheduler import SyncScheduler
            s = SyncScheduler()
        return s


    def test_on_tick_time_rollback_clears_triggered_and_logs_warning(self, scheduler, caplog):
        future_time = datetime.now() + timedelta(hours=2)
        scheduler._last_check_time = future_time
        scheduler._triggered_tasks = {'task_a', 'task_b', 'task_c'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with caplog.at_level(logging.WARNING, logger='app.core.scheduler'):
                scheduler._on_tick()

        assert len(scheduler._triggered_tasks) == 0
        assert any('时间回拨' in record.message for record in caplog.records)

    def test_on_tick_time_rollback_updates_last_check_time(self, scheduler):
        future_time = datetime.now() + timedelta(hours=1)
        scheduler._last_check_time = future_time

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            scheduler._on_tick()

        assert scheduler._last_check_time is not None
        assert scheduler._last_check_time <= datetime.now()


    def test_on_tick_invalid_cron_does_not_affect_other_tasks(self, scheduler, qtbot):
        mock_croniter = MagicMock()
        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=5)

        call_count = [0]

        def croniter_side_effect(expr, base=None):
            call_count[0] += 1
            if expr == 'invalid_cron':
                raise ValueError("Invalid cron expression")
            return mock_itr

        scheduler._scheduled_tasks = {
            'bad_task': 'invalid_cron',
            'good_task': '0 * * * *',
        }

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=croniter_side_effect):
                with qtbot.waitSignal(scheduler.taskDue, timeout=1000):
                    scheduler._on_tick()

        assert 'good_task' in scheduler._triggered_tasks

    def test_on_tick_invalid_cron_logs_error(self, scheduler, caplog):
        scheduler._scheduled_tasks = {'bad_task': 'not_a_cron'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=ValueError("Invalid")):
                with caplog.at_level(logging.ERROR, logger='app.core.scheduler'):
                    scheduler._on_tick()

        assert any('bad_task' in record.message for record in caplog.records)


    def test_on_tick_callback_called_when_task_due(self, scheduler):
        mock_callback = MagicMock()
        scheduler.set_check_callback(mock_callback)

        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=5)

        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                scheduler._on_tick()

        mock_callback.assert_called_once_with('task1')

    def test_on_tick_callback_exception_does_not_crash_scheduler(self, scheduler, caplog):
        error_callback = MagicMock(side_effect=RuntimeError("callback exploded"))
        scheduler.set_check_callback(error_callback)

        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=5)

        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                with caplog.at_level(logging.ERROR, logger='app.core.scheduler'):
                    scheduler._on_tick()

        error_callback.assert_called_once_with('task1')
        assert any('回调函数执行出错' in record.message for record in caplog.records)

    def test_on_tick_callback_exception_does_not_prevent_signal(self, scheduler, qtbot):
        error_callback = MagicMock(side_effect=Exception("callback error"))
        scheduler.set_check_callback(error_callback)

        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=5)

        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                with qtbot.waitSignal(scheduler.taskDue, timeout=1000):
                    scheduler._on_tick()

    def test_on_tick_no_callback_set(self, scheduler, qtbot):
        assert scheduler._check_callback is None

        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime.now() - timedelta(minutes=5)

        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                with qtbot.waitSignal(scheduler.taskDue, timeout=1000):
                    scheduler._on_tick()


    def test_on_tick_type_error_caught(self, scheduler, caplog):
        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=TypeError("bad type")):
                with caplog.at_level(logging.ERROR, logger='app.core.scheduler'):
                    scheduler._on_tick()

        assert any('类型错误' in record.message for record in caplog.records)


    def test_on_tick_generic_exception_caught(self, scheduler, caplog):
        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=RuntimeError("unexpected")):
                with caplog.at_level(logging.ERROR, logger='app.core.scheduler'):
                    scheduler._on_tick()

        assert any('未知错误' in record.message for record in caplog.records)


    def test_get_next_run_value_error_returns_none(self, scheduler):
        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=ValueError("bad cron")):
                result = scheduler.get_next_run('task1')

        assert result is None

    def test_get_next_run_type_error_returns_none(self, scheduler):
        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=TypeError("bad type")):
                result = scheduler.get_next_run('task1')

        assert result is None

    def test_get_next_run_generic_exception_returns_none(self, scheduler):
        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=RuntimeError("unexpected")):
                result = scheduler.get_next_run('task1')

        assert result is None

    def test_get_next_run_get_next_raises_returns_none(self, scheduler):
        scheduler._scheduled_tasks = {'task1': '0 * * * *'}

        mock_itr = MagicMock()
        mock_itr.get_next.side_effect = Exception("get_next failed")

        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', return_value=mock_itr):
                result = scheduler.get_next_run('task1')

        assert result is None


    def test_validate_cron_empty_string(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            assert scheduler.validate_cron('') is False

    def test_validate_cron_none_input(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            assert scheduler.validate_cron(None) is False

    def test_validate_cron_integer_input(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            assert scheduler.validate_cron(123) is False

    def test_validate_cron_list_input(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            assert scheduler.validate_cron(['0', '*', '*', '*', '*']) is False

    def test_validate_cron_whitespace_only(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=ValueError("Invalid")):
                assert scheduler.validate_cron('   ') is False

    def test_validate_cron_dict_input(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            assert scheduler.validate_cron({'cron': '0 * * * *'}) is False

    def test_validate_cron_bool_input(self, scheduler):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            assert scheduler.validate_cron(True) is False

    def test_validate_cron_generic_exception(self, scheduler, caplog):
        with patch('app.core.scheduler.CRONITER_AVAILABLE', True):
            with patch('app.core.scheduler.croniter', side_effect=RuntimeError("unexpected")):
                with caplog.at_level(logging.ERROR, logger='app.core.scheduler'):
                    result = scheduler.validate_cron('0 * * * *')

        assert result is False
        assert any('未知错误' in record.message for record in caplog.records)


    def test_clear_empties_all_state(self, scheduler):
        scheduler._scheduled_tasks = {'t1': '0 * * * *', 't2': '*/5 * * * *'}
        scheduler._last_run_times = {
            't1': datetime(2024, 1, 1, 12, 0),
            't2': datetime(2024, 6, 15, 8, 30),
        }
        scheduler._triggered_tasks = {'t1', 't2'}
        scheduler._last_check_time = datetime.now()

        scheduler.clear()

        assert scheduler._scheduled_tasks == {}
        assert scheduler._last_run_times == {}
        assert scheduler._triggered_tasks == set()
        assert scheduler._last_check_time is None

    def test_clear_on_empty_scheduler(self, scheduler):
        assert scheduler._scheduled_tasks == {}
        assert scheduler._last_run_times == {}
        assert scheduler._triggered_tasks == set()

        scheduler.clear()

        assert scheduler._scheduled_tasks == {}
        assert scheduler._last_run_times == {}
        assert scheduler._triggered_tasks == set()
        assert scheduler._last_check_time is None
