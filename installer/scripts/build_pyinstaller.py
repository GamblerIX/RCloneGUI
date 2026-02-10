#!/usr/bin/env python3
"""
PyInstaller 打包脚本 - RClone GUI
用法:
    cd installer/scripts
    python build_pyinstaller.py [--debug] [--onedir]

默认生成 onefile 模式的 exe。
"""

import argparse
import subprocess
import sys
import shutil
from pathlib import Path

# 项目根目录 = installer/scripts/../../
ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_SCRIPT = ROOT / "main.py"
DIST_DIR = ROOT / "installer" / "dist"
BUILD_DIR = ROOT / "build" / "pyinstaller"


def get_version() -> str:
    """从 pyproject.toml 读取版本号"""
    toml = ROOT / "pyproject.toml"
    for line in toml.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            return line.split('"')[1]
    return "0.0.0"


def find_package_path(package_name: str) -> Path | None:
    """定位已安装包的路径"""
    try:
        mod = __import__(package_name)
        return Path(mod.__file__).parent
    except Exception:
        return None


def build(debug: bool = False, onedir: bool = False):
    version = get_version()
    print(f"=== RClone GUI v{version} - PyInstaller 打包 ===")

    # 清理旧构建
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # ── 基础命令 ──
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(MAIN_SCRIPT),
        "--name", "RCloneGUI",
        "--workpath", str(BUILD_DIR),
        "--distpath", str(DIST_DIR),
        "--specpath", str(BUILD_DIR),
        "--clean",
        "--noconfirm",
    ]

    # onefile vs onedir
    if onedir:
        cmd.append("--onedir")
    else:
        cmd.append("--onefile")

    # 控制台
    if debug:
        cmd.append("--console")
        cmd.extend(["--debug", "all"])
    else:
        cmd.append("--noconsole")

    # ── 隐式导入 ──
    hidden_imports = [
        "qfluentwidgets",
        "qfluentwidgets.common",
        "qfluentwidgets.components",
        "qfluentwidgets.window",
        "qfluentwidgets._rc",
        "qframelesswindow",
        "qframelesswindow.windows",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtXml",
        "shiboken6",
        "croniter",
        # app 内部模块
        "app",
        "app.common",
        "app.common.config",
        "app.common.logger",
        "app.common.signal_bus",
        "app.common.auto_start",
        "app.core",
        "app.core.bootstrap",
        "app.core.config_manager",
        "app.core.mount_manager",
        "app.core.rclone",
        "app.core.scheduler",
        "app.core.sync_manager",
        "app.models",
        "app.models.mount",
        "app.models.remote",
        "app.models.sync_task",
        "app.providers",
        "app.providers.ftp",
        "app.providers.s3",
        "app.providers.sftp",
        "app.providers.smb",
        "app.providers.webdav",
        "app.views",
        "app.views.main_window",
        "app.views.home_interface",
        "app.views.remote_interface",
        "app.views.mount_interface",
        "app.views.browser_interface",
        "app.views.sync_interface",
        "app.views.settings_interface",
        "app.views.download_overlay",
    ]
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])

    # ── 数据文件：qfluentwidgets 资源 ──
    qfw_path = find_package_path("qfluentwidgets")
    if qfw_path:
        # 包含 _rc 资源目录（图标、QSS 样式等）
        rc_dir = qfw_path / "_rc"
        if rc_dir.exists():
            cmd.extend(["--add-data", f"{rc_dir}{os.pathsep}qfluentwidgets/_rc"])
        # 包含整个 qfluentwidgets 包以确保资源完整
        cmd.extend(["--add-data", f"{qfw_path}{os.pathsep}qfluentwidgets"])
        print(f"  qfluentwidgets: {qfw_path}")

    qfw_path2 = find_package_path("qframelesswindow")
    if qfw_path2:
        cmd.extend(["--add-data", f"{qfw_path2}{os.pathsep}qframelesswindow"])
        print(f"  qframelesswindow: {qfw_path2}")

    # ── 项目自带数据 ──
    config_dir = ROOT / "config"
    if config_dir.exists():
        cmd.extend(["--add-data", f"{config_dir}{os.pathsep}config"])

    env_dir = ROOT / "environments"
    if env_dir.exists():
        cmd.extend(["--add-data", f"{env_dir}{os.pathsep}environments"])

    # ── 排除不需要的 Qt 模块以减小体积 ──
    excludes = [
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DAnimation",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQml",
        "PySide6.QtBluetooth",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtRemoteObjects",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "pytest",
        "hypothesis",
        "pytest_cov",
        "pytest_mock",
        "pytest_qt",
        "_pytest",
    ]
    for exc in excludes:
        cmd.extend(["--exclude-module", exc])

    print(f"\n  命令: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        suffix = "pyinstaller"
        if onedir:
            print(f"\n✅ 构建成功: {DIST_DIR / 'RCloneGUI'}/")
        else:
            exe = DIST_DIR / "RCloneGUI.exe"
            target = DIST_DIR / f"RCloneGUI-v{version}-{suffix}.exe"
            if exe.exists():
                if target.exists():
                    target.unlink()
                exe.rename(target)
                print(f"\n✅ 构建成功: {target}")
            else:
                print(f"\n✅ 构建完成，请检查 {DIST_DIR}")
    else:
        print(f"\n❌ 构建失败，退出码: {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    import os
    parser = argparse.ArgumentParser(description="PyInstaller 打包 RClone GUI")
    parser.add_argument("--debug", action="store_true", help="启用调试模式（显示控制台）")
    parser.add_argument("--onedir", action="store_true", help="使用 onedir 模式（目录分发）")
    args = parser.parse_args()
    build(debug=args.debug, onedir=args.onedir)
