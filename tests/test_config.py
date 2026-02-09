import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestLanguage:

    def test_language_values(self):
        from app.common.config import Language

        assert Language.CHINESE_SIMPLIFIED is not None
        assert Language.ENGLISH is not None
        assert Language.AUTO is not None


class TestLanguageSerializer:

    def test_serialize_chinese(self):
        from app.common.config import Language, LanguageSerializer

        serializer = LanguageSerializer()
        result = serializer.serialize(Language.CHINESE_SIMPLIFIED)
        assert 'zh' in result.lower() or 'Chinese' in result

    def test_serialize_english(self):
        from app.common.config import Language, LanguageSerializer

        serializer = LanguageSerializer()
        result = serializer.serialize(Language.ENGLISH)
        assert 'en' in result.lower() or 'English' in result

    def test_serialize_auto(self):
        from app.common.config import Language, LanguageSerializer

        serializer = LanguageSerializer()
        result = serializer.serialize(Language.AUTO)
        assert result == "Auto"

    def test_deserialize_auto(self):
        from app.common.config import Language, LanguageSerializer

        serializer = LanguageSerializer()
        result = serializer.deserialize("Auto")
        assert result == Language.AUTO

    def test_deserialize_chinese(self):
        from app.common.config import Language, LanguageSerializer

        serializer = LanguageSerializer()
        result = serializer.deserialize("zh_CN")
        assert isinstance(result, Language)

    def test_deserialize_english(self):
        from app.common.config import Language, LanguageSerializer

        serializer = LanguageSerializer()
        result = serializer.deserialize("en_US")
        assert isinstance(result, Language)


class TestGetAppPath:

    def test_frozen_app(self):
        from app.common.config import get_app_path

        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, 'executable', '/path/to/app.exe'):
                result = get_app_path()
                assert result == Path('/path/to')

    def test_development_app(self):
        from app.common.config import get_app_path

        with patch.object(sys, 'frozen', False, create=True):
            result = get_app_path()
            assert 'app' in str(result).lower() or 'RCloneGUI' in str(result)


class TestConfig:

    def test_config_items_exist(self):
        from app.common.config import Config

        config = Config()

        assert hasattr(config, 'rclonePath')
        assert hasattr(config, 'rcloneConfigPath')

        assert hasattr(config, 'autoMount')
        assert hasattr(config, 'cacheDirMode')

        assert hasattr(config, 'autoStart')
        assert hasattr(config, 'minimizeToTray')
        assert hasattr(config, 'closeToTray')

        assert hasattr(config, 'themeMode')

        assert hasattr(config, 'language')




class TestGetConfig:

    def test_get_config_singleton(self):
        from app.common.config import get_config, _cfg

        import app.common.config as config_module
        original_cfg = config_module._cfg
        config_module._cfg = None

        try:
            cfg1 = get_config()
            cfg2 = get_config()
            assert cfg1 is cfg2
        finally:
            config_module._cfg = original_cfg

    def test_get_config_thread_safety(self):
        from app.common.config import get_config
        import threading

        import app.common.config as config_module
        original_cfg = config_module._cfg
        config_module._cfg = None

        configs = []
        lock = threading.Lock()

        def get_and_store():
            cfg = get_config()
            with lock:
                configs.append(cfg)

        try:
            threads = [threading.Thread(target=get_and_store) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(set(id(c) for c in configs)) == 1
        finally:
            config_module._cfg = original_cfg


class TestConfigProxy:

    def test_proxy_getattr(self):
        from app.common.config import _ConfigProxy, cfg

        result = cfg.rclonePath
        assert result is not None

    def test_proxy_setattr(self):
        from app.common.config import _ConfigProxy

        proxy = _ConfigProxy()
        proxy._instance = MagicMock()
        assert proxy._instance is not None

    def test_proxy_dir(self):
        from app.common.config import cfg

        attrs = dir(cfg)
        assert 'rclonePath' in attrs
        assert 'themeMode' in attrs


class TestGetCacheDir:
    """测试 get_cache_dir 函数的所有分支。"""

    def test_default_mode_returns_default_cache_dir(self):
        from app.common.config import get_cache_dir, CacheDirMode, DEFAULT_CACHE_DIR
        from unittest.mock import patch, MagicMock

        mock_config = MagicMock()
        mock_config.cacheDirMode.value = CacheDirMode.DEFAULT
        with patch('app.common.config.get_config', return_value=mock_config):
            result = get_cache_dir()
            assert result == str(DEFAULT_CACHE_DIR)

    def test_system_temp_mode_returns_empty_string(self):
        from app.common.config import get_cache_dir, CacheDirMode
        from unittest.mock import patch, MagicMock

        mock_config = MagicMock()
        mock_config.cacheDirMode.value = CacheDirMode.SYSTEM_TEMP
        with patch('app.common.config.get_config', return_value=mock_config):
            result = get_cache_dir()
            assert result == ''

    def test_custom_mode_with_path_returns_custom_path(self):
        from app.common.config import get_cache_dir, CacheDirMode
        from unittest.mock import patch, MagicMock

        mock_config = MagicMock()
        mock_config.cacheDirMode.value = CacheDirMode.CUSTOM
        mock_config.cacheDirCustomPath.value = 'C:\\my_cache'
        with patch('app.common.config.get_config', return_value=mock_config):
            result = get_cache_dir()
            assert result == 'C:\\my_cache'

    def test_custom_mode_without_path_returns_default(self):
        from app.common.config import get_cache_dir, CacheDirMode, DEFAULT_CACHE_DIR
        from unittest.mock import patch, MagicMock

        mock_config = MagicMock()
        mock_config.cacheDirMode.value = CacheDirMode.CUSTOM
        mock_config.cacheDirCustomPath.value = ''
        with patch('app.common.config.get_config', return_value=mock_config):
            result = get_cache_dir()
            assert result == str(DEFAULT_CACHE_DIR)


class TestConfigProxySetattr:
    """测试 _ConfigProxy.__setattr__ 的 else 分支。"""

    def test_proxy_setattr_delegates_to_instance(self):
        from app.common.config import _ConfigProxy
        from unittest.mock import MagicMock

        proxy = _ConfigProxy()
        mock_instance = MagicMock()
        proxy._instance = mock_instance

        # 设置非 _instance 属性应委托给实例
        proxy.rclonePath = 'new_path'
        assert mock_instance.rclonePath == 'new_path'


class TestEnumSerializer:
    """测试 EnumSerializer 的序列化和反序列化。"""

    def test_serialize(self):
        from app.common.config import EnumSerializer, CacheDirMode

        serializer = EnumSerializer(CacheDirMode)
        assert serializer.serialize(CacheDirMode.DEFAULT) == 'default'
        assert serializer.serialize(CacheDirMode.SYSTEM_TEMP) == 'system'
        assert serializer.serialize(CacheDirMode.CUSTOM) == 'custom'

    def test_deserialize(self):
        from app.common.config import EnumSerializer, CacheDirMode

        serializer = EnumSerializer(CacheDirMode)
        assert serializer.deserialize('default') == CacheDirMode.DEFAULT
        assert serializer.deserialize('system') == CacheDirMode.SYSTEM_TEMP
        assert serializer.deserialize('custom') == CacheDirMode.CUSTOM
