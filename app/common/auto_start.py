import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Union, List

logger = logging.getLogger(__name__)


def get_app_executable_path() -> Union[str, List[str]]:
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        app_dir = Path(__file__).parent.parent.parent
        main_script = app_dir / 'main.py'
        if main_script.exists():
            current_exe = Path(sys.executable)
            pythonw_exe = current_exe.parent / 'pythonw.exe'

            if not pythonw_exe.exists():
                pythonw_exe = current_exe

            return [str(pythonw_exe), str(main_script)]
        return [sys.executable]


def set_auto_start(enabled: bool) -> bool:
    if os.name != 'nt':
        return False

    try:
        import winreg

        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        app_name = 'RCloneGUI'

        if enabled:
            app_cmd = get_app_executable_path()

            if isinstance(app_cmd, list):
                app_path = subprocess.list2cmdline(app_cmd)
            else:
                app_path = str(app_cmd)

            if len(app_path) > 1024:
                logger.error("设置开机自启失败: 路径过长")
                return False

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                 winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
            winreg.CloseKey(key)
        else:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                     winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, app_name)
                winreg.CloseKey(key)
            except FileNotFoundError:
                pass

        return True
    except PermissionError:
        logger.error("设置开机自启失败: 权限不足")
        return False
    except OSError as e:
        logger.error(f"设置开机自启失败: 系统错误 {e}")
        return False
    except ImportError as e:
        logger.error(f"设置开机自启失败: 无法导入 winreg 模块 {e}")
        return False
    except Exception as e:
        logger.error(f"设置开机自启失败: 未知错误 {e}")
        return False


def is_auto_start_enabled() -> bool:
    if os.name != 'nt':
        return False

    try:
        import winreg

        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        app_name = 'RCloneGUI'

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                 winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, app_name)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False
    except Exception:
        return False


def toggle_auto_start() -> bool:
    current = is_auto_start_enabled()
    new_state = not current
    success = set_auto_start(new_state)
    return new_state if success else current
