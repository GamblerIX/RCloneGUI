"""
Mount 数据模型扩展的属性测试。

包含 Property 4、5、6，验证 Mount 模型 source 字段、序列化行为和工厂方法的正确性。
"""

import string

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from app.models.mount import Mount, MountStatus, MountSource, CacheMode


# ---------------------------------------------------------------------------
# 智能生成器：约束到 Mount 构造函数的有效输入空间
# ---------------------------------------------------------------------------

# 有效盘符策略：A-Z 的单个字母
drive_letters = st.sampled_from(list(string.ascii_uppercase))

# 有效远程名称策略：不含 '..'、'/'、'\' 的非空字符串
_name_chars = string.ascii_letters + string.digits + '_-'
remote_names = st.text(
    alphabet=_name_chars, min_size=1, max_size=20
).filter(lambda s: s[0] not in '-')

# 远程路径策略：简单路径字符串（允许空字符串）
_path_chars = string.ascii_letters + string.digits + '_/-'
remote_paths = st.text(alphabet=_path_chars, min_size=0, max_size=30)

# 有效缓存模式
cache_modes = st.sampled_from(["off", "minimal", "writes", "full"])

# 有效缓存大小：如 "10G", "512M", "1T" 等
cache_sizes = st.builds(
    lambda n, u: f"{n}{u}",
    st.integers(min_value=1, max_value=9999),
    st.sampled_from(["K", "M", "G", "T"]),
)

# 正整数进程 ID
positive_pids = st.integers(min_value=1, max_value=2**31 - 1)


# ===========================================================================
# Property 4: Mount 默认来源为 config
# ===========================================================================

# Feature: mount-and-vendor-improvements, Property 4: Mount 默认来源为 config
class TestProperty4MountDefaultSourceIsConfig:
    """**Validates: Requirements 4.1**"""

    @given(
        remote_name=remote_names,
        remote_path=remote_paths,
        drive_letter=drive_letters,
        cache_mode=cache_modes,
        vfs_cache_max_size=cache_sizes,
        auto_mount=st.booleans(),
        read_only=st.booleans(),
    )
    @settings(max_examples=100)
    def test_default_source_is_config(
        self,
        remote_name: str,
        remote_path: str,
        drive_letter: str,
        cache_mode: CacheMode,
        vfs_cache_max_size: str,
        auto_mount: bool,
        read_only: bool,
    ) -> None:
        """通过标准构造函数创建的 Mount 对象（未指定 source），其 source 应为 'config'。"""
        mount = Mount(
            remote_name=remote_name,
            remote_path=remote_path,
            drive_letter=drive_letter,
            cache_mode=cache_mode,
            vfs_cache_max_size=vfs_cache_max_size,
            auto_mount=auto_mount,
            read_only=read_only,
        )
        assert mount.source == "config", (
            f"Mount(remote_name={remote_name!r}, drive_letter={drive_letter!r}) "
            f"的 source 应为 'config'，实际为 {mount.source!r}"
        )


# ===========================================================================
# Property 5: 发现挂载不参与序列化
# ===========================================================================

# Feature: mount-and-vendor-improvements, Property 5: 发现挂载不参与序列化
class TestProperty5DiscoveredMountSerialization:
    """**Validates: Requirements 4.2**"""

    @given(
        remote_name=remote_names,
        remote_path=remote_paths,
        drive_letter=drive_letters,
        cache_mode=cache_modes,
        vfs_cache_max_size=cache_sizes,
        auto_mount=st.booleans(),
        read_only=st.booleans(),
    )
    @settings(max_examples=100)
    def test_discovered_mount_to_dict_returns_none(
        self,
        remote_name: str,
        remote_path: str,
        drive_letter: str,
        cache_mode: CacheMode,
        vfs_cache_max_size: str,
        auto_mount: bool,
        read_only: bool,
    ) -> None:
        """source 为 'discovered' 的 Mount，to_dict() 应返回 None。"""
        mount = Mount(
            remote_name=remote_name,
            remote_path=remote_path,
            drive_letter=drive_letter,
            source="discovered",
            cache_mode=cache_mode,
            vfs_cache_max_size=vfs_cache_max_size,
            auto_mount=auto_mount,
            read_only=read_only,
        )
        result = mount.to_dict()
        assert result is None, (
            f"source='discovered' 的 Mount to_dict() 应返回 None，实际返回 {result}"
        )

    @given(
        remote_name=remote_names,
        remote_path=remote_paths,
        drive_letter=drive_letters,
        cache_mode=cache_modes,
        vfs_cache_max_size=cache_sizes,
        auto_mount=st.booleans(),
        read_only=st.booleans(),
    )
    @settings(max_examples=100)
    def test_config_mount_to_dict_returns_valid_dict(
        self,
        remote_name: str,
        remote_path: str,
        drive_letter: str,
        cache_mode: CacheMode,
        vfs_cache_max_size: str,
        auto_mount: bool,
        read_only: bool,
    ) -> None:
        """source 为 'config' 的 Mount，to_dict() 应返回包含所有必需字段的有效字典。"""
        mount = Mount(
            remote_name=remote_name,
            remote_path=remote_path,
            drive_letter=drive_letter,
            source="config",
            cache_mode=cache_mode,
            vfs_cache_max_size=vfs_cache_max_size,
            auto_mount=auto_mount,
            read_only=read_only,
        )
        result = mount.to_dict()

        # 必须返回字典
        assert isinstance(result, dict), (
            f"source='config' 的 Mount to_dict() 应返回 dict，实际返回 {type(result)}"
        )

        # 验证所有必需字段存在
        required_fields = [
            'remote_name', 'remote_path', 'drive_letter', 'status',
            'auto_mount', 'read_only', 'cache_mode', 'vfs_cache_max_size',
            'process_id', 'error_message', 'source',
        ]
        for field_name in required_fields:
            assert field_name in result, (
                f"to_dict() 返回的字典缺少必需字段 '{field_name}'"
            )

        # 验证字段值与 Mount 对象一致
        assert result['remote_name'] == mount.remote_name
        assert result['drive_letter'] == mount.drive_letter.upper()
        assert result['auto_mount'] == mount.auto_mount
        assert result['read_only'] == mount.read_only
        assert result['cache_mode'] == mount.cache_mode
        assert result['source'] == "config"


# ===========================================================================
# Property 6: from_process_info 工厂方法正确性
# ===========================================================================

# Feature: mount-and-vendor-improvements, Property 6: from_process_info 工厂方法正确性
class TestProperty6FromProcessInfoCorrectness:
    """**Validates: Requirements 4.3**"""

    @given(
        drive_letter=drive_letters,
        pid=positive_pids,
    )
    @settings(max_examples=100)
    def test_from_process_info_creates_correct_mount(
        self,
        drive_letter: str,
        pid: int,
    ) -> None:
        """from_process_info(drive_letter, pid) 应返回正确属性的 Mount 对象。"""
        mount = Mount.from_process_info(drive_letter, pid)

        # source 必须为 "discovered"
        assert mount.source == "discovered", (
            f"from_process_info 创建的 Mount source 应为 'discovered'，"
            f"实际为 {mount.source!r}"
        )

        # status 必须为 MOUNTED
        assert mount.status == MountStatus.MOUNTED, (
            f"from_process_info 创建的 Mount status 应为 MOUNTED，"
            f"实际为 {mount.status}"
        )

        # drive_letter 必须为传入盘符的大写形式
        assert mount.drive_letter == drive_letter.upper(), (
            f"from_process_info 创建的 Mount drive_letter 应为 "
            f"{drive_letter.upper()!r}，实际为 {mount.drive_letter!r}"
        )

        # process_id 必须为传入的 PID
        assert mount.process_id == pid, (
            f"from_process_info 创建的 Mount process_id 应为 {pid}，"
            f"实际为 {mount.process_id}"
        )

    @given(
        drive_letter=drive_letters,
        pid=positive_pids,
    )
    @settings(max_examples=100)
    def test_from_process_info_default_remote_name(
        self,
        drive_letter: str,
        pid: int,
    ) -> None:
        """from_process_info 未指定 remote_name 时，应使用 'unknown_{drive_letter}' 占位名。"""
        mount = Mount.from_process_info(drive_letter, pid)

        expected_name = f"unknown_{drive_letter.upper()}"
        assert mount.remote_name == expected_name, (
            f"from_process_info 未指定 remote_name 时，remote_name 应为 "
            f"{expected_name!r}，实际为 {mount.remote_name!r}"
        )
