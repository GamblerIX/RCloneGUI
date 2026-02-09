"""
发现过滤逻辑 discover_system_mounts 的属性测试。

包含 Property 2，验证 discover_system_mounts() 返回的发现挂载列表中的所有盘符
都不在配置挂载的盘符集合中。

Feature: mount-and-vendor-improvements, Property 2: 发现过滤排除已配置盘符
"""

import string
from threading import Lock
from unittest.mock import patch

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.models.mount import Mount


# ---------------------------------------------------------------------------
# 智能生成器：构造配置挂载集合和系统进程列表
# ---------------------------------------------------------------------------

# 所有可用盘符
ALL_DRIVES = list(string.ascii_uppercase)

# 盘符子集策略：从 A-Z 中选取一个子集作为配置挂载的盘符
config_drive_sets = st.frozensets(
    st.sampled_from(ALL_DRIVES),
    min_size=0,
    max_size=20,
)

# 进程盘符子集策略：从 A-Z 中选取一个子集作为系统进程的盘符
process_drive_sets = st.frozensets(
    st.sampled_from(ALL_DRIVES),
    min_size=0,
    max_size=20,
)

# 进程 PID 策略：正整数
pids = st.integers(min_value=1, max_value=99999)

# 远程名称策略：简单的合法远程名
remote_names = st.from_regex(r'[A-Za-z][A-Za-z0-9_]{0,8}', fullmatch=True)


@st.composite
def config_and_process_scenario(draw):
    """生成一个测试场景：配置挂载盘符集合 + 系统进程列表。

    返回:
        (config_drives: frozenset[str], processes: list[tuple[str, int, str]])
        - config_drives: 配置挂载中使用的盘符集合
        - processes: 系统进程列表，每项为 (drive_letter, pid, remote_name)
    """
    config_drives = draw(config_drive_sets)
    process_drives = draw(process_drive_sets)

    processes = []
    for drive in sorted(process_drives):
        pid = draw(pids)
        name = draw(remote_names)
        processes.append((drive, pid, name))

    return (config_drives, processes)


# ===========================================================================
# Property 2: 发现过滤排除已配置盘符
# ===========================================================================

# Feature: mount-and-vendor-improvements, Property 2: 发现过滤排除已配置盘符
class TestProperty2DiscoverFilterExcludesConfigDrives:
    """**Validates: Requirements 1.2**"""

    @given(scenario=config_and_process_scenario())
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_discovered_mounts_exclude_config_drives(
        self,
        scenario: tuple,
    ) -> None:
        """对于任意配置挂载集合和系统进程列表，discover_system_mounts()
        返回的发现挂载列表中的所有盘符都不在配置挂载的盘符集合中。"""
        config_drives, processes = scenario

        # --- 构造 MountManager 实例（不调用 __init__，避免 QObject 依赖） ---
        from app.core.mount_manager import MountManager

        manager = MountManager.__new__(MountManager)
        manager.mounts = {}
        manager._lock = Lock()

        # 填充配置挂载：为每个配置盘符创建一个 source="config" 的 Mount
        for drive in config_drives:
            remote = f"config_remote_{drive}"
            mount = Mount(
                remote_name=remote,
                remote_path="",
                drive_letter=drive,
                source="config",
            )
            manager.mounts[remote] = mount

        # 使用 unittest.mock.patch 替代 mocker fixture，
        # 确保每次 hypothesis 迭代都正确 mock
        with patch.object(manager, '_query_rclone_mount_processes',
                          return_value=processes), \
             patch('app.core.mount_manager.os.name', 'nt'):

            # --- 执行 ---
            discovered = manager.discover_system_mounts()

        # --- 验证核心属性 ---
        # 属性：所有发现挂载的盘符都不在配置盘符集合中
        for mount in discovered:
            assert mount.drive_letter not in config_drives, (
                f"发现挂载的盘符 {mount.drive_letter!r} 不应在配置盘符集合 "
                f"{config_drives!r} 中，但它出现了。"
                f"\n进程列表: {processes!r}"
            )

        # 补充验证：发现挂载的盘符集合应恰好等于进程盘符中不在配置盘符中的部分
        expected_drives = {d for d, _, _ in processes} - set(config_drives)
        actual_drives = {m.drive_letter for m in discovered}
        assert actual_drives == expected_drives, (
            f"发现挂载的盘符集合应为 {expected_drives!r}，"
            f"实际为 {actual_drives!r}。"
            f"\n配置盘符: {config_drives!r}"
            f"\n进程列表: {processes!r}"
        )

        # 补充验证：所有发现挂载的 source 应为 "discovered"
        for mount in discovered:
            assert mount.source == "discovered", (
                f"发现挂载的 source 应为 'discovered'，"
                f"实际为 {mount.source!r}"
            )
