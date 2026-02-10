import sys
import threading
from pathlib import Path
from enum import Enum

from PySide6.QtCore import QLocale
from qfluentwidgets import (
    QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
    OptionsValidator, Theme, ConfigSerializer, EnumSerializer as _ThemeEnumSerializer, qconfig
)


class Language(Enum):
    CHINESE_SIMPLIFIED = QLocale(QLocale.Chinese, QLocale.China)
    ENGLISH = QLocale(QLocale.English)
    AUTO = QLocale()


class LanguageSerializer(ConfigSerializer):

    def serialize(self, language):
        return language.value.name() if language != Language.AUTO else "Auto"

    def deserialize(self, value: str):
        return Language(QLocale(value)) if value != "Auto" else Language.AUTO


class EnumSerializer(ConfigSerializer):

    def __init__(self, enum_class):
        self.enum_class = enum_class

    def serialize(self, value):
        return value.value

    def deserialize(self, value: str):
        return self.enum_class(value)


def get_app_path():
    if getattr(sys, 'frozen', False):
        # Nuitka onefile: __compiled__.containing_dir 指向原始 exe 所在目录
        # 而 sys.executable 在 Nuitka onefile 下指向临时解压目录
        compiled = globals().get('__compiled__', None)
        if compiled and hasattr(compiled, 'containing_dir'):
            return Path(compiled.containing_dir)
        # PyInstaller: sys.executable 直接指向原始 exe
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


class CacheDirMode(Enum):
    DEFAULT = "default"
    SYSTEM_TEMP = "system"
    CUSTOM = "custom"


class Config(QConfig):

    rclonePath = ConfigItem("RClone", "Path", "environments/rclone.exe")
    rcloneConfigPath = ConfigItem("RClone", "ConfigPath", "config/rclone.conf")

    autoMount = ConfigItem("Mount", "AutoMount", False, BoolValidator())
    cacheDirMode = OptionsConfigItem(
        "Mount", "CacheDirMode", CacheDirMode.DEFAULT,
        OptionsValidator(CacheDirMode), EnumSerializer(CacheDirMode)
    )
    cacheDirCustomPath = ConfigItem("Mount", "CacheDirCustomPath", "")

    autoStart = ConfigItem("App", "AutoStart", False, BoolValidator())
    minimizeToTray = ConfigItem("App", "MinimizeToTray", False, BoolValidator())
    closeToTray = ConfigItem("App", "CloseToTray", False, BoolValidator())

    themeMode = OptionsConfigItem(
        "QFluentWidgets", "ThemeMode", Theme.AUTO,
        OptionsValidator(Theme), _ThemeEnumSerializer(Theme)
    )

    language = OptionsConfigItem(
        "App", "Language", Language.AUTO,
        OptionsValidator(Language), LanguageSerializer()
    )


APP_PATH = get_app_path()
CONFIG_PATH = APP_PATH / "config" / "config.json"
DEFAULT_CACHE_DIR = APP_PATH / "cache"


def get_cache_dir() -> str:
    mode = get_config().cacheDirMode.value
    if mode == CacheDirMode.DEFAULT:
        return str(DEFAULT_CACHE_DIR)
    elif mode == CacheDirMode.SYSTEM_TEMP:
        return ""
    elif mode == CacheDirMode.CUSTOM:
        return get_config().cacheDirCustomPath.value or str(DEFAULT_CACHE_DIR)
    return str(DEFAULT_CACHE_DIR)

_cfg: Config | None = None
_config_lock = threading.Lock()


def get_config() -> Config:
    global _cfg
    if _cfg is None:
        with _config_lock:
            if _cfg is None:
                _cfg = Config()
                config_path = Path(str(CONFIG_PATH))
                first_run = not config_path.exists()
                qconfig.load(str(CONFIG_PATH), _cfg)
                if first_run:
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    _cfg.save()
    return _cfg


def get_system_theme():
    if sys.platform == 'win32':
        try:
            import winreg
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return Theme.LIGHT if value == 1 else Theme.DARK
        except Exception:
            pass
    return Theme.LIGHT


class _ConfigProxy:
    _instance: Config | None = None

    def _get_instance(self) -> Config:
        if self._instance is None:
            self._instance = get_config()
        return self._instance

    def __getattr__(self, name: str):
        return getattr(self._get_instance(), name)

    def __setattr__(self, name: str, value):
        if name in ('_instance',):
            super().__setattr__(name, value)
        else:
            setattr(self._get_instance(), name, value)

    def __dir__(self):
        return dir(self._get_instance())


cfg = _ConfigProxy()
