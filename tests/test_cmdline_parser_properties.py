"""
命令行解析函数 _parse_rclone_mount_cmdline 的属性测试。

包含 Property 1，验证解析函数能从有效的 rclone mount 命令行中正确提取盘符和远程存储名称。

Feature: mount-and-vendor-improvements, Property 1: 命令行解析正确提取盘符和远程名
"""

import string

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.core.mount_manager import _parse_rclone_mount_cmdline


# ---------------------------------------------------------------------------
# 智能生成器：构造有效的 rclone mount 命令行字符串
# ---------------------------------------------------------------------------

# 有效盘符策略：A-Z 的单个大写字母
drive_letters = st.sampled_from(list(string.ascii_uppercase))

# 有效远程名称策略：符合正则 [A-Za-z0-9_][A-Za-z0-9_.@\-]* 的字符串
# 使用 from_regex 确保生成的名称完全匹配解析器期望的格式
remote_names = st.from_regex(r'[A-Za-z0-9_][A-Za-z0-9_.@\-]{0,10}', fullmatch=True)

# 远程路径策略：可选的路径部分（不含空白字符）
remote_paths = st.from_regex(r'[A-Za-z0-9_/.\-]{0,15}', fullmatch=True)

# rclone 可执行文件前缀策略
rclone_prefixes = st.sampled_from([
    'rclone',
    'rclone.exe',
    '"C:\\Program Files\\rclone\\rclone.exe"',
    '"C:\\Users\\test\\rclone.exe"',
    'C:\\rclone\\rclone.exe',
])

# 可选的命令行选项策略
rclone_options = st.sampled_from([
    '',
    ' --vfs-cache-mode full',
    ' --vfs-cache-mode writes --vfs-cache-max-size 10G',
    ' --allow-other',
    ' --log-level DEBUG',
    ' --read-only',
])


@st.composite
def valid_rclone_mount_cmdlines(draw):
    """生成有效的 rclone mount 命令行字符串。

    格式: {rclone_prefix} mount {remote_name}:{path} {drive_letter}: {options}

    返回 (cmdline, expected_drive_letter, expected_remote_name) 三元组。
    """
    prefix = draw(rclone_prefixes)
    remote_name = draw(remote_names)
    path = draw(remote_paths)
    drive_letter = draw(drive_letters)
    options = draw(rclone_options)

    # 构造命令行
    remote_part = f"{remote_name}:{path}" if path else f"{remote_name}:"
    cmdline = f"{prefix} mount {remote_part} {drive_letter}:{options}"

    return (cmdline, drive_letter.upper(), remote_name)


# ===========================================================================
# Property 1: 命令行解析正确提取盘符和远程名
# ===========================================================================

# Feature: mount-and-vendor-improvements, Property 1: 命令行解析正确提取盘符和远程名
class TestProperty1CmdlineParserExtractsDriveAndRemote:
    """**Validates: Requirements 1.1**"""

    @given(data=valid_rclone_mount_cmdlines())
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_parser_extracts_drive_letter_and_remote_name(
        self,
        data: tuple,
    ) -> None:
        """对于任意有效的 rclone mount 命令行，解析函数应正确提取盘符和远程名。"""
        cmdline, expected_drive, expected_remote = data

        result = _parse_rclone_mount_cmdline(cmdline)

        # 解析不应失败
        assert result is not None, (
            f"解析有效命令行应返回非 None 结果，cmdline={cmdline!r}"
        )

        actual_drive, actual_remote = result

        # 盘符应为大写字母 A-Z
        assert actual_drive == expected_drive, (
            f"盘符应为 {expected_drive!r}，实际为 {actual_drive!r}，"
            f"cmdline={cmdline!r}"
        )

        # 远程名称应正确提取
        assert actual_remote == expected_remote, (
            f"远程名应为 {expected_remote!r}，实际为 {actual_remote!r}，"
            f"cmdline={cmdline!r}"
        )

        # 盘符必须是单个大写字母
        assert len(actual_drive) == 1 and actual_drive in string.ascii_uppercase, (
            f"盘符应为单个大写字母 A-Z，实际为 {actual_drive!r}"
        )
