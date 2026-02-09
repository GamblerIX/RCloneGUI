import pytest
from unittest.mock import MagicMock, patch
import sys


class TestSignalBus:

    def test_signal_bus_singleton(self):
        from app.common.signal_bus import signalBus
        from app.common.signal_bus import SignalBus

        assert isinstance(signalBus, SignalBus)

    def test_signal_bus_has_theme_signal(self):
        from app.common.signal_bus import signalBus

        assert hasattr(signalBus, 'themeChanged')

    def test_signal_bus_has_remote_signals(self):
        from app.common.signal_bus import signalBus

        assert hasattr(signalBus, 'remoteAdded')
        assert hasattr(signalBus, 'remoteRemoved')
        assert hasattr(signalBus, 'remoteUpdated')

    def test_signal_bus_has_mount_signals(self):
        from app.common.signal_bus import signalBus

        assert hasattr(signalBus, 'mountStarted')
        assert hasattr(signalBus, 'mountStopped')
        assert hasattr(signalBus, 'mountError')

    def test_signal_bus_has_sync_signals(self):
        from app.common.signal_bus import signalBus

        assert hasattr(signalBus, 'syncStarted')
        assert hasattr(signalBus, 'syncProgress')
        assert hasattr(signalBus, 'syncCompleted')
        assert hasattr(signalBus, 'syncError')

    def test_signal_bus_has_navigation_signals(self):
        from app.common.signal_bus import signalBus

        assert hasattr(signalBus, 'switchToInterface')

    def test_signal_bus_has_tray_signals(self):
        from app.common.signal_bus import signalBus

        assert hasattr(signalBus, 'showMainWindow')
        assert hasattr(signalBus, 'hideMainWindow')


class TestConfig:

    def test_config_singleton(self):
        from app.common.config import cfg, Config, _ConfigProxy

        assert isinstance(cfg, _ConfigProxy)

    def test_config_has_rclone_settings(self):
        from app.common.config import cfg

        assert hasattr(cfg, 'rclonePath')
        assert hasattr(cfg, 'rcloneConfigPath')

    def test_config_has_mount_settings(self):
        from app.common.config import cfg

        assert hasattr(cfg, 'autoMount')
        assert hasattr(cfg, 'cacheDirMode')

    def test_config_has_app_settings(self):
        from app.common.config import cfg

        assert hasattr(cfg, 'autoStart')
        assert hasattr(cfg, 'minimizeToTray')
        assert hasattr(cfg, 'closeToTray')
        assert hasattr(cfg, 'themeMode')
        assert hasattr(cfg, 'language')

    def test_get_app_path_not_frozen(self):
        from app.common.config import get_app_path
        from pathlib import Path

        path = get_app_path()

        assert isinstance(path, Path)
        assert path.exists()

    def test_get_app_path_frozen(self, monkeypatch):
        monkeypatch.setattr(sys, 'frozen', True, raising=False)
        monkeypatch.setattr(sys, 'executable', '/path/to/app.exe')

        from app.common import config
        import importlib
        importlib.reload(config)

        path = config.get_app_path()
        assert path is not None

    def test_app_path_defined(self):
        from app.common.config import APP_PATH
        from pathlib import Path

        assert isinstance(APP_PATH, Path)

    def test_config_path_defined(self):
        from app.common.config import CONFIG_PATH
        from pathlib import Path

        assert isinstance(CONFIG_PATH, Path)
        assert 'config.json' in str(CONFIG_PATH)


class TestLanguage:

    def test_language_enum_values(self):
        from app.common.config import Language

        assert hasattr(Language, 'CHINESE_SIMPLIFIED')
        assert hasattr(Language, 'ENGLISH')
        assert hasattr(Language, 'AUTO')

    def test_language_serializer_serialize(self):
        from app.common.config import LanguageSerializer, Language

        serializer = LanguageSerializer()

        result = serializer.serialize(Language.AUTO)
        assert result == 'Auto'

        result = serializer.serialize(Language.ENGLISH)
        assert isinstance(result, str)

    def test_language_serializer_deserialize(self):
        from app.common.config import LanguageSerializer, Language

        serializer = LanguageSerializer()

        result = serializer.deserialize('Auto')
        assert result == Language.AUTO

        result = serializer.deserialize('en_US')
        assert isinstance(result, Language)
