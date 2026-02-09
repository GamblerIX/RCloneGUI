import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open


class TestGetAppExecutablePath:

    def test_frozen_executable(self):
        from app.common.auto_start import get_app_executable_path

        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, 'executable', '/path/to/app.exe'):
                result = get_app_executable_path()
                assert result == '/path/to/app.exe'

    def test_development_environment(self):
        from app.common.auto_start import get_app_executable_path

        with patch.object(sys, 'frozen', False, create=True):
            with patch.object(sys, 'executable', '/python/python.exe'):
                with patch('pathlib.Path.exists', return_value=True):
                    result = get_app_executable_path()
                    assert isinstance(result, list)
                    assert len(result) == 2
                    assert 'main.py' in result[1]

    def test_development_pythonw_not_found(self):
        from app.common.auto_start import get_app_executable_path

        with patch.object(sys, 'frozen', False, create=True):
            with patch.object(sys, 'executable', '/python/python.exe'):
                call_count = [0]
                def exists_side_effect(self):
                    call_count[0] += 1
                    return call_count[0] == 1

                with patch('pathlib.Path.exists', exists_side_effect):
                    result = get_app_executable_path()
                    assert isinstance(result, list)
                    assert 'python.exe' in result[0]


class TestSetAutoStart:

    def test_non_windows_platform(self):
        from app.common.auto_start import set_auto_start

        with patch('os.name', 'posix'):
            result = set_auto_start(True)
            assert result is False

    @patch('os.name', 'nt')
    def test_enable_auto_start_success(self):
        from app.common.auto_start import set_auto_start

        mock_key = MagicMock()
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002
        mock_winreg.REG_SZ = 1

        with patch.dict('sys.modules', {'winreg': mock_winreg}):
            with patch.object(sys, 'frozen', True, create=True):
                with patch.object(sys, 'executable', '/path/to/app.exe'):
                    result = set_auto_start(True)
                    assert result is True
                    mock_winreg.SetValueEx.assert_called_once()

    @patch('os.name', 'nt')
    def test_disable_auto_start_success(self):
        from app.common.auto_start import set_auto_start

        mock_key = MagicMock()
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002

        with patch.dict('sys.modules', {'winreg': mock_winreg}):
            result = set_auto_start(False)
            assert result is True
            mock_winreg.DeleteValue.assert_called_once()

    @patch('os.name', 'nt')
    def test_disable_auto_start_key_not_found(self):
        from app.common.auto_start import set_auto_start

        mock_key = MagicMock()
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_SET_VALUE = 0x0002
        mock_winreg.DeleteValue.side_effect = FileNotFoundError()

        with patch.dict('sys.modules', {'winreg': mock_winreg}):
            result = set_auto_start(False)
            assert result is True

    @patch('os.name', 'nt')
    def test_enable_auto_start_permission_error(self):
        from app.common.auto_start import set_auto_start

        mock_winreg = MagicMock()
        mock_winreg.OpenKey.side_effect = PermissionError()

        with patch.dict('sys.modules', {'winreg': mock_winreg}):
            result = set_auto_start(True)
            assert result is False

    @patch('os.name', 'nt')
    def test_enable_auto_start_path_too_long(self):
        from app.common.auto_start import set_auto_start

        with patch('app.common.auto_start.get_app_executable_path',
                   return_value='x' * 1025):
            result = set_auto_start(True)
            assert result is False

    @patch('os.name', 'nt')
    def test_enable_auto_start_os_error(self):
        from app.common.auto_start import set_auto_start

        mock_winreg = MagicMock()
        mock_winreg.OpenKey.side_effect = OSError("Registry error")

        with patch.dict('sys.modules', {'winreg': mock_winreg}):
            result = set_auto_start(True)
            assert result is False


class TestIsAutoStartEnabled:

    def test_non_windows_platform(self):
        from app.common.auto_start import is_auto_start_enabled

        with patch('os.name', 'posix'):
            result = is_auto_start_enabled()
            assert result is False

    @patch('os.name', 'nt')
    def test_auto_start_enabled(self):
        from app.common.auto_start import is_auto_start_enabled

        mock_key = MagicMock()
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019
        mock_winreg.QueryValueEx.return_value = ('/path/to/app.exe', 1)

        with patch.dict('sys.modules', {'winreg': mock_winreg}):
            result = is_auto_start_enabled()
            assert result is True

    @patch('os.name', 'nt')
    def test_auto_start_disabled(self):
        from app.common.auto_start import is_auto_start_enabled

        mock_key = MagicMock()
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()

        with patch.dict('sys.modules', {'winreg': mock_winreg}):
            result = is_auto_start_enabled()
            assert result is False

    @patch('os.name', 'nt')
    def test_auto_start_error(self):
        from app.common.auto_start import is_auto_start_enabled

        mock_winreg = MagicMock()
        mock_winreg.OpenKey.side_effect = Exception("Registry error")

        with patch.dict('sys.modules', {'winreg': mock_winreg}):
            result = is_auto_start_enabled()
            assert result is False


class TestToggleAutoStart:

    def test_toggle_from_disabled(self):
        from app.common.auto_start import toggle_auto_start

        with patch('app.common.auto_start.is_auto_start_enabled', return_value=False):
            with patch('app.common.auto_start.set_auto_start', return_value=True):
                result = toggle_auto_start()
                assert result is True

    def test_toggle_from_enabled(self):
        from app.common.auto_start import toggle_auto_start

        with patch('app.common.auto_start.is_auto_start_enabled', return_value=True):
            with patch('app.common.auto_start.set_auto_start', return_value=True):
                result = toggle_auto_start()
                assert result is False

    def test_toggle_failure(self):
        from app.common.auto_start import toggle_auto_start

        with patch('app.common.auto_start.is_auto_start_enabled', return_value=False):
            with patch('app.common.auto_start.set_auto_start', return_value=False):
                result = toggle_auto_start()
                assert result is False
