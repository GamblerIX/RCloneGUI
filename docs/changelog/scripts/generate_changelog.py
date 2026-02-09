#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Changelog 自动生成脚本

从 git 历史自动生成 changelog，写入 docs/changelog/{version}.md。
用于 GitHub Actions CD 工作流自动发布。

用法:
    python docs/changelog/scripts/generate_changelog.py --version v0.1.0
    python docs/changelog/scripts/generate_changelog.py --version v0.1.0 --builder nuitka
    python docs/changelog/scripts/generate_changelog.py --version v0.1.0 --builder pyinstaller
    python docs/changelog/scripts/generate_changelog.py --version v0.1.0 --builder both
"""

import argparse
import subprocess
import sys
import os
from datetime import datetime, timezone, timedelta


def run_git(args: list[str], *, allow_fail: bool = False, stdin_data: bytes | None = None) -> str:
    """执行 git 命令并返回 stdout（去除首尾空白）。"""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=False,  # 使用 bytes 模式以支持 stdin_data
        input=stdin_data,
    )
    stdout = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        if allow_fail:
            return ""
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        print(f"[错误] git {' '.join(args)} 失败:\n{stderr}", file=sys.stderr)
        sys.exit(1)
    return stdout


def get_empty_tree_hash() -> str:
    """获取 git 空树的哈希值（跨平台兼容）。"""
    return run_git(["hash-object", "-t", "tree", "--stdin"], stdin_data=b"")


def get_previous_tag() -> str | None:
    """
    获取上一个 git tag。
    如果没有任何 tag，返回 None（表示从第一个 commit 开始）。
    """
    # 方法1: 尝试获取 HEAD 之前最近的 tag
    result = run_git(["describe", "--tags", "--abbrev=0", "HEAD^"], allow_fail=True)
    if result:
        return result

    # 方法2: 按创建时间排序获取所有 tag
    result = run_git(["tag", "--sort=-creatordate"], allow_fail=True)
    if result:
        tags = result.splitlines()
        if tags:
            return tags[0]

    return None


def get_commits(prev_tag: str | None) -> list[str]:
    """获取从上一个 tag 到 HEAD 之间的 commit 消息列表（按时间正序）。"""
    if prev_tag:
        output = run_git(["log", f"{prev_tag}..HEAD", "--pretty=format:%s", "--reverse"])
    else:
        # 没有 tag，获取所有 commit
        output = run_git(["log", "--pretty=format:%s", "--reverse"])

    if not output:
        return []
    return output.splitlines()


def get_changed_files(prev_tag: str | None, diff_filter: str) -> list[str]:
    """
    获取文件变更列表。
    diff_filter: A=新增, M=变更, D=移除
    """
    if prev_tag:
        output = run_git(["diff", "--name-only", f"--diff-filter={diff_filter}", f"{prev_tag}..HEAD"])
    else:
        # 没有 tag，对比空树和 HEAD（即所有文件都是"新增"）
        empty_tree = get_empty_tree_hash()
        output = run_git(["diff", "--name-only", f"--diff-filter={diff_filter}", empty_tree, "HEAD"])

    if not output:
        return []
    return output.splitlines()


def build_file_list(files: list[str]) -> str:
    """将文件列表格式化为 markdown 列表项。如果为空则返回 '- 无'。"""
    if not files:
        return "- 无"
    return "\n".join(f"- {f}" for f in files)


def build_commit_list(commits: list[str]) -> str:
    """将 commit 列表格式化为编号列表。如果为空则返回 '1. 无'。"""
    if not commits:
        return "1. 无"
    return "\n".join(f"{i}. {msg}" for i, msg in enumerate(commits, 1))


def build_release_files(version: str, builder: str) -> str:
    """根据 builder 参数生成发布文件列表。"""
    files = []

    if builder in ("nuitka", "both"):
        files.append(f"- RCloneGUI-{version}-nuitka.exe")
    if builder in ("pyinstaller", "both"):
        files.append(f"- RCloneGUI-{version}-pyinstaller.exe")

    # 始终包含安装包
    files.append(f"- RCloneGUI-{version}-setup.exe")

    return "\n".join(files)


def generate_changelog(version: str, builder: str) -> str:
    """生成完整的 changelog 内容。"""

    # 获取上一个 tag
    prev_tag = get_previous_tag()

    if prev_tag:
        print(f"[信息] 上一个 tag: {prev_tag}")
    else:
        print("[信息] 没有找到上一个 tag，将从第一个 commit 开始统计")

    # 当前日期（UTC+8 北京时间）
    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz).strftime("%Y-%m-%d")

    # 获取 commit 消息
    commits = get_commits(prev_tag)

    # 获取文件变更
    added_files = get_changed_files(prev_tag, "A")
    modified_files = get_changed_files(prev_tag, "M")
    deleted_files = get_changed_files(prev_tag, "D")

    # 生成发布文件列表
    release_files = build_release_files(version, builder)

    # 组装 changelog（按模板格式，去掉模板说明行）
    changelog = f"""# {today} {version} 

## 文件变更

### 新增

{build_file_list(added_files)}

### 变更

{build_file_list(modified_files)}

### 移除

{build_file_list(deleted_files)}

## 提交消息

{build_commit_list(commits)}

## 发布文件

{release_files}

## 快速开始

{{keep}}
"""

    return changelog


def main():
    parser = argparse.ArgumentParser(
        description="从 git 历史自动生成 changelog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python docs/changelog/scripts/generate_changelog.py --version v0.1.0
    python docs/changelog/scripts/generate_changelog.py --version v0.1.0 --builder nuitka
    python docs/changelog/scripts/generate_changelog.py --version v0.1.0 --builder both
        """,
    )
    parser.add_argument(
        "--version",
        required=True,
        help="版本号，如 v0.1.0",
    )
    parser.add_argument(
        "--builder",
        choices=["nuitka", "pyinstaller", "both"],
        default="both",
        help="打包工具 (默认: both)",
    )

    args = parser.parse_args()

    # 生成 changelog 内容
    changelog_content = generate_changelog(args.version, args.builder)

    # 确定输出路径：使用 git 获取仓库根目录
    try:
        repo_root = run_git(["rev-parse", "--show-toplevel"])
    except SystemExit:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    output_dir = os.path.join(repo_root, "docs", "changelog")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"{args.version}.md")

    # 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(changelog_content)

    print(f"[完成] Changelog 已生成: {output_path}")
    print(f"  版本: {args.version}")
    print(f"  打包工具: {args.builder}")


if __name__ == "__main__":
    main()
