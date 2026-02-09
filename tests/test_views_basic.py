
import os
import sys
import logging
import pytest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCloseEvent


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _mock_view_deps(mocker):
    mock_rclone_instance = MagicMock()
    mock_rclone_instance.version.return_value = 'rclone v1.0.0'
    mock_rclone_instance.rclone_path = '/usr/bin/rclone'
    mock_rclone_instance.config_path = '/tmp/rclone.conf'
    mock_rclone_instance.config_dump.return_value = {}
    mock_rclone_instance.listremotes.return_value = []

    for mod in [
        'app.views.home_interface.RClone',
        'app.views.mount_interface.RClone',
        'app.views.remote_interface.RClone',
        'app.views.browser_interface.RClone',
        'app.views.sync_interface.RClone',
        'app.views.settings_interface.RClone',
    ]:
        mocker.patch(mod, return_value=mock_rclone_instance)

    mock_cm_instance = MagicMock()
    mock_cm_instance.list_remotes.return_value = []
    for mod in [
        'app.views.home_interface.ConfigManager',
        'app.views.mount_interface.ConfigManager',
        'app.views.remote_interface.ConfigManager',
        'app.views.browser_interface.ConfigManager',
        'app.views.sync_interface.ConfigManager',
    ]:
        mocker.patch(mod, return_value=mock_cm_instance)

    mock_mm_instance = MagicMock()
    mock_mm_instance.mounts = {}
    mock_mm_instance.load_mounts.return_value = None
    for mod in [
        'app.views.home_interface.MountManager',
        'app.views.mount_interface.MountManager',
    ]:
        mocker.patch(mod, return_value=mock_mm_instance)

    mock_sm_instance = MagicMock()
    mock_sm_instance.tasks = {}
    mock_sm_instance.load_tasks.return_value = True
    mocker.patch('app.views.sync_interface.SyncManager', return_value=mock_sm_instance)

    mocker.patch('app.views.settings_interface.is_auto_start_enabled', return_value=False)
    mocker.patch('app.views.settings_interface.set_auto_start', return_value=True)

    return {
        'rclone': mock_rclone_instance,
        'config_manager': mock_cm_instance,
        'mount_manager': mock_mm_instance,
        'sync_manager': mock_sm_instance,
    }


class TestGetSystemTheme:

    def test_non_windows_returns_light(self, mocker):
        mocker.patch.object(sys, 'platform', 'linux')
        from app.common.config import get_system_theme
        from qfluentwidgets import Theme
        result = get_system_theme()
        assert result == Theme.LIGHT

    def test_non_windows_darwin_returns_light(self, mocker):
        mocker.patch.object(sys, 'platform', 'darwin')
        from app.common.config import get_system_theme
        from qfluentwidgets import Theme
        result = get_system_theme()
        assert result == Theme.LIGHT

    def test_settings_get_system_theme_non_windows(self, mocker):
        mocker.patch.object(sys, 'platform', 'linux')
        from app.common.config import get_system_theme
        from qfluentwidgets import Theme
        result = get_system_theme()
        assert result == Theme.LIGHT


class TestStatCard:

    def test_set_value_updates_label(self):
        from qfluentwidgets import FluentIcon as FIF
        from app.views.home_interface import StatCard

        card = StatCard(FIF.CLOUD, '测试', '0')
        assert card.valueLabel.text() == '0'

        card.setValue('42')
        assert card.valueLabel.text() == '42'

    def test_set_value_empty_string(self):
        from qfluentwidgets import FluentIcon as FIF
        from app.views.home_interface import StatCard

        card = StatCard(FIF.CLOUD, '测试', '10')
        card.setValue('')
        assert card.valueLabel.text() == ''

    def test_set_value_multiple_times(self):
        from qfluentwidgets import FluentIcon as FIF
        from app.views.home_interface import StatCard

        card = StatCard(FIF.CLOUD, '测试', '0')
        for i in range(5):
            card.setValue(str(i))
        assert card.valueLabel.text() == '4'


class TestMainWindow:

    @pytest.fixture
    def main_window(self, mocker):
        _mock_view_deps(mocker)

        from app.views.main_window import MainWindow
        window = MainWindow()
        yield window
        window.close()

    def test_switch_to_valid_interface(self, main_window):
        valid_names = ['home', 'remote', 'mount', 'browser', 'sync', 'settings']
        for name in valid_names:
            main_window.switchToInterface(name)

    def test_switch_to_invalid_interface(self, main_window):
        main_window.switchToInterface('nonexistent')
        main_window.switchToInterface('')
        main_window.switchToInterface('invalid_name')

    def test_close_event_close_to_tray(self, main_window, mocker):
        mock_cfg = MagicMock()
        mock_cfg.closeToTray.value = True
        mocker.patch('app.views.main_window.cfg', mock_cfg)

        event = MagicMock(spec=QCloseEvent)
        main_window.closeEvent(event)

        event.ignore.assert_called_once()

    def test_close_event_no_tray(self, main_window, mocker):
        mock_cfg = MagicMock()
        mock_cfg.closeToTray.value = False
        mocker.patch('app.views.main_window.cfg', mock_cfg)

        event = MagicMock(spec=QCloseEvent)
        main_window.closeEvent(event)

        event.accept.assert_called_once()


class TestHomeInterface:

    def test_load_data_exception(self, mocker):
        mock_rclone_instance = MagicMock()
        mock_rclone_instance.version.return_value = 'rclone v1.0.0'
        mocker.patch('app.views.home_interface.RClone', return_value=mock_rclone_instance)

        mock_cm_instance = MagicMock()
        mock_cm_instance.list_remotes.side_effect = RuntimeError("Connection failed")
        mocker.patch('app.views.home_interface.ConfigManager', return_value=mock_cm_instance)

        mock_mm_instance = MagicMock()
        mock_mm_instance.mounts = {}
        mocker.patch('app.views.home_interface.MountManager', return_value=mock_mm_instance)

        mock_infobar = mocker.patch('app.views.home_interface.InfoBar')

        import app.common.logger as logger_module
        if not hasattr(logger_module, 'logger'):
            logger_module.logger = logging.getLogger('RCloneGUI')
            _cleanup_logger = True
        else:
            _cleanup_logger = False

        try:
            from app.views.home_interface import HomeInterface
            interface = HomeInterface()

            mock_infobar.warning.assert_called_once()
        finally:
            if _cleanup_logger:
                delattr(logger_module, 'logger')

    def test_load_data_success(self, mocker):
        mock_rclone_instance = MagicMock()
        mock_rclone_instance.version.return_value = 'rclone v1.0.0'
        mocker.patch('app.views.home_interface.RClone', return_value=mock_rclone_instance)

        mock_cm_instance = MagicMock()
        mock_cm_instance.list_remotes.return_value = [MagicMock(), MagicMock(), MagicMock()]
        mocker.patch('app.views.home_interface.ConfigManager', return_value=mock_cm_instance)

        mock_mm_instance = MagicMock()
        mock_mount1 = MagicMock()
        mock_mount1.is_mounted = True
        mock_mount2 = MagicMock()
        mock_mount2.is_mounted = False
        mock_mm_instance.mounts = {'m1': mock_mount1, 'm2': mock_mount2}
        mocker.patch('app.views.home_interface.MountManager', return_value=mock_mm_instance)

        from app.views.home_interface import HomeInterface
        interface = HomeInterface()

        assert interface.remoteCard.valueLabel.text() == '3'
        assert interface.mountCard.valueLabel.text() == '1'


class TestViewInstantiation:

    @pytest.fixture(autouse=True)
    def mock_dependencies(self, mocker):
        _mock_view_deps(mocker)

    def test_home_interface_instantiation(self):
        from app.views.home_interface import HomeInterface
        interface = HomeInterface()
        assert interface is not None
        assert interface.objectName() == 'homeInterface'

    def test_mount_interface_instantiation(self):
        from app.views.mount_interface import MountInterface
        interface = MountInterface()
        assert interface is not None
        assert interface.objectName() == 'mountInterface'

    def test_remote_interface_instantiation(self):
        from app.views.remote_interface import RemoteInterface
        interface = RemoteInterface()
        assert interface is not None
        assert interface.objectName() == 'remoteInterface'

    def test_browser_interface_instantiation(self):
        from app.views.browser_interface import BrowserInterface
        interface = BrowserInterface()
        assert interface is not None
        assert interface.objectName() == 'browserInterface'

    def test_sync_interface_instantiation(self):
        from app.views.sync_interface import SyncInterface
        interface = SyncInterface()
        assert interface is not None
        assert interface.objectName() == 'syncInterface'

    def test_settings_interface_instantiation(self):
        from app.views.settings_interface import SettingsInterface
        interface = SettingsInterface()
        assert interface is not None
        assert interface.objectName() == 'settingsInterface'

    def test_stat_card_instantiation(self):
        from qfluentwidgets import FluentIcon as FIF
        from app.views.home_interface import StatCard
        card = StatCard(FIF.CLOUD, '测试标题', '0')
        assert card is not None
        assert card.titleLabel.text() == '测试标题'
        assert card.valueLabel.text() == '0'

    def test_quick_action_card_instantiation(self):
        from qfluentwidgets import FluentIcon as FIF
        from app.views.home_interface import QuickActionCard
        card = QuickActionCard(FIF.ADD, '标题', '描述', '按钮')
        assert card is not None
        assert card.titleLabel.text() == '标题'
        assert card.descLabel.text() == '描述'

    def test_main_window_instantiation(self, mocker):
        from app.views.main_window import MainWindow
        window = MainWindow()
        assert window is not None
        assert window.windowTitle() == 'RClone GUI'
        window.close()
