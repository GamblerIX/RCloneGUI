import pytest
import logging
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, mock_open
import threading


class TestAppLogger:

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        from app.common.logger import AppLogger
        AppLogger._instance = None
        AppLogger._initialized = False
        yield
        AppLogger._instance = None
        AppLogger._initialized = False

    def test_singleton(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            logger1 = AppLogger()
            logger2 = AppLogger()
            assert logger1 is logger2

    def test_logger_property(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()
            logger = app_logger.logger
            assert isinstance(logger, logging.Logger)
            assert logger.name == 'RCloneGUI'

    def test_log_methods(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()

            with patch.object(app_logger._logger, 'debug') as mock_debug:
                app_logger.debug('debug message')
                mock_debug.assert_called_once_with('debug message')

            with patch.object(app_logger._logger, 'info') as mock_info:
                app_logger.info('info message')
                mock_info.assert_called_once_with('info message')

            with patch.object(app_logger._logger, 'warning') as mock_warning:
                app_logger.warning('warning message')
                mock_warning.assert_called_once_with('warning message')

            with patch.object(app_logger._logger, 'error') as mock_error:
                app_logger.error('error message')
                mock_error.assert_called_once_with('error message')

            with patch.object(app_logger._logger, 'critical') as mock_critical:
                app_logger.critical('critical message')
                mock_critical.assert_called_once_with('critical message')

    def test_get_log_dir(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()
            log_dir = app_logger.get_log_dir()
            assert log_dir == tmp_path / 'logs'
            assert log_dir.exists()

    def test_get_log_files(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()
            log_dir = tmp_path / 'logs'
            log_dir.mkdir(exist_ok=True)

            (log_dir / 'app.log').touch()
            (log_dir / 'error.log').touch()

            files = app_logger.get_log_files()
            assert len(files) == 2

    def test_get_log_files_empty(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()
            with patch.object(app_logger, '_log_dir', tmp_path / 'non_existent_logs'):
                files = app_logger.get_log_files()
                assert files == []

    def test_clear_old_logs(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()
            log_dir = tmp_path / 'logs'

            old_log = log_dir / 'old.log'
            old_log.touch()

            old_time = datetime.now() - timedelta(days=60)
            with patch('app.common.logger.datetime') as mock_datetime:
                mock_datetime.now.return_value = old_time
                mock_datetime.fromtimestamp = datetime.fromtimestamp

                import time
                old_timestamp = time.mktime(old_time.timetuple())
                import os
                os.utime(old_log, (old_timestamp, old_timestamp))

            with patch.object(app_logger._logger, 'info') as mock_info:
                app_logger.clear_old_logs(days=30)
                assert not old_log.exists()

    @pytest.mark.skip(reason="Cannot mock WindowsPath attributes in Windows")
    def test_clear_old_logs_error(self, tmp_path):
        pass

    def test_read_log_content(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()
            log_dir = tmp_path / 'logs'

            log_content = "Line 1\nLine 2\nLine 3\n"
            (log_dir / 'app.log').write_text(log_content, encoding='utf-8')

            result = app_logger.read_log_content('app.log', lines=2)
            assert 'Line 2' in result
            assert 'Line 3' in result
            assert 'Line 1' not in result

    def test_read_log_content_file_not_exists(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()

            result = app_logger.read_log_content('nonexistent.log')
            assert '不存在' in result or 'not exist' in result.lower()

    def test_read_log_content_error(self, tmp_path):
        from app.common.logger import AppLogger

        with patch('app.common.logger.APP_PATH', tmp_path):
            app_logger = AppLogger()
            log_dir = tmp_path / 'logs'
            (log_dir / 'app.log').touch()

            with patch('builtins.open', side_effect=IOError('Read error')):
                result = app_logger.read_log_content('app.log')
                assert '失败' in result or 'error' in result.lower()


class TestGetLogger:

    def test_get_logger_with_name(self):
        from app.common.logger import get_logger

        logger = get_logger('test_module')
        assert isinstance(logger, logging.Logger)
        assert logger.name == 'RCloneGUI.test_module'

    def test_get_logger_without_name(self):
        from app.common.logger import get_logger, app_logger

        logger = get_logger()
        assert logger is app_logger.logger
