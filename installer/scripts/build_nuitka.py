#!/usr/bin/env python3
"""
Nuitka 打包脚本 - RClone GUI
用法:
    cd installer/scripts
    python build_nuitka.py [--debug] [--standalone]

默认生成 onefile 模式的 exe。
--standalone 生成目录模式（调试更方便）。
"""

import argparse
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_SCRIPT = ROOT / "main.py"
DIST_DIR = ROOT / "installer" / "dist"
BUILD_DIR = ROOT / "build" / "nuitka"


def get_version() -> str:
    toml = ROOT / "pyproject.toml"
    for line in toml.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            return line.split('"')[1]
    return "0.0.0"


def find_package_path(package_name: str) -> Path | None:
    try:
        mod = __import__(package_name)
        return Path(mod.__file__).parent
    except Exception:
        return None


def build(debug: bool = False, standalone: bool = False):
    version = get_version()
    print(f"=== RClone GUI v{version} - Nuitka 打包 ===")

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        str(MAIN_SCRIPT),
        "--enable-plugin=pyside6",
        f"--output-dir={BUILD_DIR}",
        "--output-filename=RCloneGUI.exe",
        "--assume-yes-for-downloads",
        f"--product-name=RClone GUI",
        f"--file-description=RClone GUI Application",
        f"--company-name=RCloneGUI",
        f"--product-version={version}",
        f"--file-version={version}",
        "--follow-imports",
    ]

    # 模式选择
    if standalone:
        cmd.append("--standalone")
    else:
        cmd.append("--onefile")

    # 控制台
    if debug:
        pass  # 默认有控制台
    else:
        cmd.append("--windows-console-mode=disable")

    # ── 包含 qfluentwidgets 及其资源 ──
    qfw_path = find_package_path("qfluentwidgets")
    if qfw_path:
        cmd.append(f"--include-package=qfluentwidgets")
        # _rc 资源已通过 --include-package 包含，无需单独 --include-data-dir
        print(f"  qfluentwidgets: {qfw_path}")

    qfw_path2 = find_package_path("qframelesswindow")
    if qfw_path2:
        cmd.append(f"--include-package=qframelesswindow")
        print(f"  qframelesswindow: {qfw_path2}")

    # ── 包含 app 包 ──
    cmd.append("--include-package=app")

    # ── 包含 croniter ──
    cmd.append("--include-package=croniter")

    # ── 项目数据文件 ──
    config_dir = ROOT / "config"
    if config_dir.exists():
        cmd.append(f"--include-data-dir={config_dir}=config")

    env_dir = ROOT / "environments"
    if env_dir.exists():
        # --include-data-dir 会跳过 .exe/.dll，所以只用 --include-data-files
        rclone_exe = env_dir / "rclone.exe"
        if rclone_exe.exists():
            cmd.append(f"--include-data-files={rclone_exe}=environments/rclone.exe")
        # 包含目录中其他非二进制数据文件（如果有的话）
        non_binary = [f for f in env_dir.iterdir() if f.is_file() and f.suffix not in ('.exe', '.dll')]
        if non_binary:
            cmd.append(f"--include-data-dir={env_dir}=environments")

    # ── 排除不需要的模块 ──
    noinclude = [
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQml",
        "PySide6.QtBluetooth",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PyQt6",
        "numpy",
        "pytest",
        "hypothesis",
        "unittest",
    ]
    for mod in noinclude:
        cmd.append(f"--nofollow-import-to={mod}")

    # ── deployment 模式（关闭 Nuitka 的安全检查提示） ──
    cmd.append("--deployment")

    print(f"\n  命令: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        # Nuitka onefile 输出到 build/nuitka/main.dist 或直接 build/nuitka/
        # 查找生成的 exe
        exe_candidates = list(BUILD_DIR.rglob("RCloneGUI.exe"))
        if not exe_candidates:
            exe_candidates = list(BUILD_DIR.rglob("main.exe"))

        if exe_candidates:
            src_exe = exe_candidates[0]
            target = DIST_DIR / f"RCloneGUI-v{version}-nuitka.exe"
            if target.exists():
                target.unlink()
            shutil.copy2(src_exe, target)
            print(f"\n✅ 构建成功: {target}")
        else:
            print(f"\n✅ 构建完成，请在 {BUILD_DIR} 中查找输出")
    else:
        print(f"\n❌ 构建失败，退出码: {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nuitka 打包 RClone GUI")
    parser.add_argument("--debug", action="store_true", help="启用调试模式（保留控制台）")
    parser.add_argument("--standalone", action="store_true", help="使用 standalone 目录模式")
    args = parser.parse_args()
    build(debug=args.debug, standalone=args.standalone)
