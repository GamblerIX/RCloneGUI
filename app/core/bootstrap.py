
import os
import sys
import platform
import struct
import zipfile
import tempfile
import shutil
import urllib.request
import json
from pathlib import Path


MIN_BUILD_NUMBER = 19044


class BootstrapError(Exception):
    pass


def check_windows_version():
    if sys.platform != "win32":
        return

    version = platform.version()
    try:
        build = int(version.split(".")[-1])
    except (ValueError, IndexError):
        return

    if build < MIN_BUILD_NUMBER:
        raise BootstrapError(
            f"当前系统版本 (Build {build}) 过低，\n"
            f"RClone GUI 要求 Windows 10 21H2 (Build {MIN_BUILD_NUMBER}) 及以上版本。"
        )


def _get_arch():
    bits = struct.calcsize("P") * 8
    machine = platform.machine().lower()

    if machine in ("amd64", "x86_64", "x64"):
        return "amd64"
    elif machine in ("arm64", "aarch64"):
        return "arm64"
    elif machine in ("x86", "i386", "i686") and bits == 32:
        return "386"
    else:
        raise BootstrapError(f"不支持的系统架构: {machine} ({bits}bit)")


def _get_latest_rclone_download_url(arch: str) -> tuple[str, str]:
    api_url = "https://api.github.com/repos/rclone/rclone/releases/latest"
    target_suffix = f"-windows-{arch}.zip"

    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise BootstrapError(f"无法获取 rclone 最新版本信息: {e}")

    tag = data.get("tag_name", "unknown")

    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(target_suffix):
            return asset["browser_download_url"], tag

    raise BootstrapError(
        f"在 rclone {tag} 的发布资源中未找到 windows-{arch} 版本"
    )


def _download_and_extract_rclone(url: str, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_exe = dest_dir / "rclone.exe"

    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="rclone_download_")
        zip_path = os.path.join(tmp_dir, "rclone.zip")

        print(f"正在下载 rclone: {url}")
        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            exe_entry = None
            for name in zf.namelist():
                if name.endswith("rclone.exe"):
                    exe_entry = name
                    break

            if exe_entry is None:
                raise BootstrapError("下载的 zip 中未找到 rclone.exe")

            zf.extract(exe_entry, tmp_dir)
            extracted_exe = os.path.join(tmp_dir, exe_entry)
            shutil.move(extracted_exe, str(dest_exe))

        print(f"rclone 已下载到: {dest_exe}")

    except BootstrapError:
        raise
    except Exception as e:
        raise BootstrapError(f"下载 rclone 失败: {e}")
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def ensure_rclone(rclone_path: str | Path):
    rclone_path = Path(rclone_path)

    if rclone_path.is_file():
        return

    print(f"未找到 rclone: {rclone_path}，正在自动下载...")

    arch = _get_arch()
    url, tag = _get_latest_rclone_download_url(arch)
    print(f"最新版本: {tag} ({arch})")

    _download_and_extract_rclone(url, rclone_path.parent)


def get_rclone_path() -> Path:
    """返回 rclone 可执行文件的绝对路径。"""
    from app.common.config import cfg, APP_PATH
    rclone_rel = cfg.rclonePath.value
    return Path(rclone_rel) if Path(rclone_rel).is_absolute() else APP_PATH / rclone_rel


def is_rclone_available() -> bool:
    """检查 rclone 是否已存在。"""
    return get_rclone_path().is_file()


def bootstrap():
    """启动前检查。仅做系统版本校验，不再自动下载 rclone。

    rclone 的下载由 GUI 层在主窗口显示后处理，以便展示下载进度遮罩。
    """
    try:
        check_windows_version()
    except BootstrapError as e:
        return False, str(e)

    return True, None
