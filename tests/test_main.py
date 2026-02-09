import pytest
from unittest.mock import MagicMock, patch
import sys


class TestMainModule:

    def test_main_import(self):
        import main
        assert main is not None
        assert hasattr(main, 'SystemTray')
        assert hasattr(main, 'main')
        assert hasattr(main, 'check_single_instance')
        assert hasattr(main, 'create_local_server')

    def test_system_tray_import(self):
        from main import SystemTray
        assert SystemTray is not None

    def test_main_function_exists(self):
        from main import main
        assert callable(main)


class TestSystemTray:

    def test_system_tray_has_init_menu(self):
        from main import SystemTray
        assert hasattr(SystemTray, 'initMenu')

    def test_system_tray_has_on_activated(self):
        from main import SystemTray
        assert hasattr(SystemTray, 'onActivated')

    def test_system_tray_has_show_window(self):
        from main import SystemTray
        assert hasattr(SystemTray, 'showWindow')

    def test_system_tray_has_mount_all(self):
        from main import SystemTray
        assert hasattr(SystemTray, 'mountAll')

    def test_system_tray_has_unmount_all(self):
        from main import SystemTray
        assert hasattr(SystemTray, 'unmountAll')

    def test_system_tray_has_exit_app(self):
        from main import SystemTray
        assert hasattr(SystemTray, 'exitApp')
