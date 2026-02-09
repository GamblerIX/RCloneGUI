"""
发现挂载 UI 的属性测试和单元测试。

包含 Property 3，验证 source 为 "discovered" 的 Mount 对象对应的 MountCard
满足：状态标签包含 "外部挂载"、编辑按钮隐藏、删除按钮隐藏、操作按钮显示 "卸载"。

Feature: mount-and-vendor-improvements, Property 3: 发现挂载卡片显示规则
"""

import os
import sys
import string

import pytest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.models.mount import Mount, MountStatus


# ---------------------------------------------------------------------------
# QApplication fixture（模块级别，确保 Qt 环境可用）
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# 智能生成器：构造 source="discovered" 的 Mount 对象
# ---------------------------------------------------------------------------

# 盘符策略：A-Z 中的单个字母
drive_letters = st.sampled_from(list(string.ascii_uppercase))

# 进程 PID 策略：正整数
pids = st.integers(min_value=1, max_value=99999)

# 远程名称策略：合法的远程名（字母开头，可包含字母数字和下划线）
remote_names = st.from_regex(r'[A-Za-z][A-Za-z0-9_]{0,8}', fullmatch=True)


@st.composite
def discovered_mount_strategy(draw):
    """生成一个 source="discovered" 的 Mount 对象。

    使用 Mount.from_process_info 工厂方法创建，确保与实际代码路径一致。
    """
    drive = draw(drive_letters)
    pid = draw(pids)
    # 随机决定是否提供远程名称
    use_remote_name = draw(st.booleans())
    if use_remote_name:
        name = draw(remote_names)
    else:
        name = ""  # from_process_info 会生成 unknown_{drive} 占位名

    mount = Mount.from_process_info(drive, pid, name)
    return mount


# ===========================================================================
# Property 3: 发现挂载卡片显示规则
# ===========================================================================

# Feature: mount-and-vendor-improvements, Property 3: 发现挂载卡片显示规则
class TestProperty3DiscoveredMountCardDisplay:
    """**Validates: Requirements 2.2, 2.3, 2.4**"""

    @given(mount=discovered_mount_strategy())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_discovered_mount_card_display_rules(self, mount: Mount) -> None:
        """对于任意 source 为 "discovered" 的 Mount 对象，其对应的 MountCard 应满足：
        状态标签包含 "外部挂载"、编辑按钮隐藏、删除按钮隐藏、操作按钮显示 "卸载"。
        """
        from app.views.mount_interface import MountCard

        card = MountCard(mount)

        # 属性 1：状态标签包含 "外部挂载"
        assert "外部挂载" in card.statusLabel.text(), (
            f"状态标签应包含 '外部挂载'，实际为 {card.statusLabel.text()!r}。"
            f"\nMount: drive={mount.drive_letter}, remote={mount.remote_name}, "
            f"source={mount.source}"
        )

        # 属性 2：编辑按钮隐藏
        assert card.editBtn.isHidden(), (
            f"编辑按钮应隐藏，但当前可见。"
            f"\nMount: drive={mount.drive_letter}, remote={mount.remote_name}"
        )

        # 属性 3：删除按钮隐藏
        assert card.deleteBtn.isHidden(), (
            f"删除按钮应隐藏，但当前可见。"
            f"\nMount: drive={mount.drive_letter}, remote={mount.remote_name}"
        )

        # 属性 4：操作按钮显示 "卸载"
        assert card.actionBtn.text() == "卸载", (
            f"操作按钮应显示 '卸载'，实际为 {card.actionBtn.text()!r}。"
            f"\nMount: drive={mount.drive_letter}, remote={mount.remote_name}"
        )

        # 清理 widget
        card.deleteLater()


# ===========================================================================
# 单元测试：发现挂载卸载流程、卸载失败错误提示
# ===========================================================================

def _mock_view_deps(mocker):
    """Mock MountInterface 的依赖项，与现有测试模式一致。"""
    mock_rclone = MagicMock()
    mock_rclone.version.return_value = "rclone v1.0.0"
    mock_rclone.rclone_path = "/usr/bin/rclone"
    mock_rclone.config_path = "/tmp/rclone.conf"
    mock_rclone.config_dump.return_value = {}
    mock_rclone.listremotes.return_value = []
    for mod in [
        "app.views.mount_interface.RClone",
    ]:
        mocker.patch(mod, return_value=mock_rclone)

    mock_cm = MagicMock()
    mock_cm.list_remotes.return_value = []
    for mod in [
        "app.views.mount_interface.ConfigManager",
    ]:
        mocker.patch(mod, return_value=mock_cm)

    mock_mm = MagicMock()
    mock_mm.mounts = {}
    mock_mm.load_mounts.return_value = None
    mock_mm.refresh_mount_status.return_value = None
    mocker.patch("app.views.mount_interface.MountManager", return_value=mock_mm)

    return {
        "rclone": mock_rclone,
        "config_manager": mock_cm,
        "mount_manager": mock_mm,
    }


class TestDiscoveredMountUnmountFlow:
    """单元测试：发现挂载异步卸载流程。

    doUnmount 现在通过 _DiscoveredUnmountWorker QThread 异步执行卸载，
    信号直接发射 _discovered_{drive} key（不再通过 remote_name 查找）。

    **Validates: Requirements 3.1, 3.2**
    """

    @pytest.fixture
    def deps(self, mocker):
        return _mock_view_deps(mocker)

    @pytest.fixture
    def iface(self, deps):
        from app.views.mount_interface import MountInterface
        return MountInterface()

    def test_doUnmount_starts_worker_for_discovered_mount(self, iface, mocker):
        """doUnmount 应为发现挂载启动 _DiscoveredUnmountWorker。"""
        from threading import Lock

        discovered_mount = Mount.from_process_info("X", 12345, "myremote")
        discovered_key = "_discovered_X"

        iface.mountManager.mounts = {discovered_key: discovered_mount}
        iface.mountManager._lock = Lock()

        mock_worker_cls = mocker.patch(
            "app.views.mount_interface._DiscoveredUnmountWorker"
        )
        mock_worker_instance = MagicMock()
        mock_worker_cls.return_value = mock_worker_instance

        iface.doUnmount(discovered_key)

        mock_worker_cls.assert_called_once_with(iface.mountManager, discovered_key)
        mock_worker_instance.start.assert_called_once()

    def test_doUnmount_disables_unmount_buttons(self, iface, mocker):
        """doUnmount 启动卸载时应禁用所有卸载按钮和全部卸载按钮。"""
        from threading import Lock
        from app.views.mount_interface import MountCard

        discovered_mount = Mount.from_process_info("X", 12345, "myremote")
        discovered_key = "_discovered_X"

        iface.mountManager.mounts = {discovered_key: discovered_mount}
        iface.mountManager._lock = Lock()

        # 加载卡片到 UI
        card = MountCard(discovered_mount)
        iface.mountCards[card._mount_key] = card

        mock_worker_cls = mocker.patch(
            "app.views.mount_interface._DiscoveredUnmountWorker"
        )
        mock_worker_cls.return_value = MagicMock()

        iface.doUnmount(discovered_key)

        assert not card.actionBtn.isEnabled()
        assert not iface.unmountAllBtn.isEnabled()

    def test_on_finished_success_removes_mount_and_refreshes(self, iface):
        """卸载成功回调应从 mounts 字典中移除并刷新 UI。"""
        from threading import Lock

        discovered_mount = Mount.from_process_info("X", 12345, "myremote")
        discovered_key = "_discovered_X"

        iface.mountManager.mounts = {discovered_key: discovered_mount}
        iface.mountManager._lock = Lock()

        iface._onDiscoveredUnmountFinished(discovered_key, True)

        assert discovered_key not in iface.mountManager.mounts
        iface.mountManager.refresh_mount_status.assert_called()

    def test_on_finished_success_clears_worker_ref(self, iface):
        """卸载成功回调应清除 _unmount_worker 引用。"""
        from threading import Lock

        discovered_mount = Mount.from_process_info("A", 111, "rem")
        discovered_key = "_discovered_A"

        iface.mountManager.mounts = {discovered_key: discovered_mount}
        iface.mountManager._lock = Lock()
        iface._unmount_worker = MagicMock()

        iface._onDiscoveredUnmountFinished(discovered_key, True)

        assert iface._unmount_worker is None


class TestDiscoveredMountUnmountFailure:
    """单元测试：发现挂载卸载失败错误提示。

    **Validates: Requirements 3.3**
    """

    @pytest.fixture
    def deps(self, mocker):
        return _mock_view_deps(mocker)

    @pytest.fixture
    def iface(self, deps):
        from app.views.mount_interface import MountInterface
        return MountInterface()

    def test_on_finished_failure_shows_error(self, iface, mocker):
        """卸载失败回调应显示 InfoBar 错误提示。"""
        from threading import Lock

        mock_infobar = mocker.patch("app.views.mount_interface.InfoBar")

        discovered_mount = Mount.from_process_info("Z", 99999, "fail_remote")
        discovered_key = "_discovered_Z"

        iface.mountManager.mounts = {discovered_key: discovered_mount}
        iface.mountManager._lock = Lock()

        iface._onDiscoveredUnmountFinished(discovered_key, False)

        mock_infobar.error.assert_called_once()
        call_args = mock_infobar.error.call_args
        assert "Z" in call_args[0][1] or "Z" in str(call_args)

    def test_on_finished_failure_keeps_mount_in_dict(self, iface, mocker):
        """卸载失败时，发现挂载应保留在 mounts 字典中。"""
        from threading import Lock

        mocker.patch("app.views.mount_interface.InfoBar")

        discovered_mount = Mount.from_process_info("W", 88888, "keep_remote")
        discovered_key = "_discovered_W"

        iface.mountManager.mounts = {discovered_key: discovered_mount}
        iface.mountManager._lock = Lock()

        iface._onDiscoveredUnmountFinished(discovered_key, False)

        assert discovered_key in iface.mountManager.mounts

    def test_on_finished_failure_clears_worker_ref(self, iface, mocker):
        """卸载失败回调也应清除 _unmount_worker 引用。"""
        from threading import Lock

        mocker.patch("app.views.mount_interface.InfoBar")

        discovered_mount = Mount.from_process_info("V", 77777, "v_remote")
        discovered_key = "_discovered_V"

        iface.mountManager.mounts = {discovered_key: discovered_mount}
        iface.mountManager._lock = Lock()
        iface._unmount_worker = MagicMock()

        iface._onDiscoveredUnmountFinished(discovered_key, False)

        assert iface._unmount_worker is None

    def test_on_finished_failure_restores_buttons(self, iface, mocker):
        """卸载失败回调应恢复所有卸载按钮为可用状态。"""
        from threading import Lock
        from app.views.mount_interface import MountCard

        mocker.patch("app.views.mount_interface.InfoBar")

        discovered_mount = Mount.from_process_info("R", 66666, "r_remote")
        discovered_key = "_discovered_R"

        iface.mountManager.mounts = {discovered_key: discovered_mount}
        iface.mountManager._lock = Lock()

        # 模拟卡片已加载且按钮已禁用
        card = MountCard(discovered_mount)
        iface.mountCards[card._mount_key] = card
        iface.unmountAllBtn.setEnabled(False)
        card.actionBtn.setEnabled(False)

        iface._onDiscoveredUnmountFinished(discovered_key, False)

        assert card.actionBtn.isEnabled()
        assert iface.unmountAllBtn.isEnabled()


# ===========================================================================
# 单元测试：同名异盘支持（_mount_key 标识）
# ===========================================================================

class TestSameNameDifferentDrive:
    """单元测试：同一 remote_name 挂载到不同盘符时，卡片独立标识。"""

    def test_discovered_mount_card_key_uses_drive(self):
        """发现挂载的 _mount_key 应为 _discovered_{drive}。"""
        from app.views.mount_interface import MountCard

        mount_a = Mount.from_process_info("A", 100, "WebDAV1")
        mount_b = Mount.from_process_info("B", 200, "WebDAV1")

        card_a = MountCard(mount_a)
        card_b = MountCard(mount_b)

        assert card_a._mount_key == "_discovered_A"
        assert card_b._mount_key == "_discovered_B"
        assert card_a._mount_key != card_b._mount_key

        card_a.deleteLater()
        card_b.deleteLater()

    def test_config_mount_card_key_uses_remote_name(self):
        """配置挂载的 _mount_key 应为 remote_name。"""
        from app.views.mount_interface import MountCard

        mount = Mount(remote_name="myremote", remote_path="", drive_letter="C")
        card = MountCard(mount)

        assert card._mount_key == "myremote"
        card.deleteLater()

    def test_unmount_signal_emits_discovered_key(self):
        """发现挂载卡片的卸载信号应发射 _discovered_{drive} key。"""
        from app.views.mount_interface import MountCard

        mount = Mount.from_process_info("A", 100, "WebDAV1")
        card = MountCard(mount)

        received = []
        card.unmountClicked.connect(received.append)
        card.actionBtn.click()

        assert received == ["_discovered_A"]
        card.deleteLater()

    def test_same_name_mounts_emit_different_keys(self):
        """同名异盘的两张卡片应发射不同的卸载信号。"""
        from app.views.mount_interface import MountCard

        mount_a = Mount.from_process_info("A", 100, "WebDAV1")
        mount_b = Mount.from_process_info("B", 200, "WebDAV1")

        card_a = MountCard(mount_a)
        card_b = MountCard(mount_b)

        received_a = []
        received_b = []
        card_a.unmountClicked.connect(received_a.append)
        card_b.unmountClicked.connect(received_b.append)

        card_a.actionBtn.click()
        card_b.actionBtn.click()

        assert received_a == ["_discovered_A"]
        assert received_b == ["_discovered_B"]

        card_a.deleteLater()
        card_b.deleteLater()
