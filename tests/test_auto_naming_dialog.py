"""对话框集成的单元测试：验证自动命名在 AddRemoteDialog 中的行为
Requirements: 1.1, 2.1, 2.2, 4.1, 4.2, 5.1
"""
import os
import sys
import pytest
from unittest.mock import MagicMock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _mock_deps(mocker):
    mock_rclone = MagicMock()
    mock_rclone.config_dump.return_value = {}
    mock_rclone.listremotes.return_value = []
    mocker.patch('app.views.remote_interface.RClone', return_value=mock_rclone)
    mock_cm = MagicMock()
    mock_cm.list_remotes.return_value = []
    mocker.patch('app.views.remote_interface.ConfigManager', return_value=mock_cm)


class TestAutoNamingDialog:

    def _make_dialog(self, mocker, remote=None, existing_names=None):
        _mock_deps(mocker)
        from app.views.remote_interface import AddRemoteDialog
        return AddRemoteDialog(parent=None, remote=remote, existing_names=existing_names)

    def test_add_mode_name_not_empty(self, mocker):
        """需求 1.1: 添加模式下名称字段自动填充"""
        dialog = self._make_dialog(mocker)
        assert dialog.nameEdit.text() != ''
        # 自动命名基于第一个提供商类型（Registry 按模块名字母序发现）
        first_type_id = dialog.typeCombo.currentData()
        from app.providers import get_provider
        first_name = get_provider(first_type_id)['name']
        import re
        expected_base = re.sub(r'[^a-zA-Z0-9_-]', '', first_name)
        assert dialog.nameEdit.text() == f'{expected_base}1'
        dialog.close()

    def test_type_switch_updates_name(self, mocker):
        """需求 2.1: 切换类型时自动更新名称"""
        dialog = self._make_dialog(mocker)
        # 初始名称基于第一个提供商类型
        initial_name = dialog.nameEdit.text()
        assert initial_name != ''
        # 切换到 SFTP
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'sftp':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert dialog.nameEdit.text() == 'SFTP1'
        dialog.close()

    def test_manual_edit_preserves_on_type_switch(self, mocker):
        """需求 2.2, 4.1, 4.2: 手动修改后切换类型保留名称"""
        dialog = self._make_dialog(mocker)
        # 模拟用户手动编辑
        dialog.nameEdit.textEdited.emit('my-custom-name')
        dialog.nameEdit.setText('my-custom-name')
        assert dialog._name_manually_edited is True
        # 切换类型
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'sftp':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert dialog.nameEdit.text() == 'my-custom-name'
        dialog.close()

    def test_edit_mode_no_auto_naming(self, mocker):
        """需求 5.1: 编辑模式不触发自动命名"""
        from app.models.remote import Remote
        remote = Remote(name='my-webdav', type='webdav', config={'url': 'https://example.com'})
        dialog = self._make_dialog(mocker, remote=remote)
        assert dialog.nameEdit.text() == 'my-webdav'
        dialog.close()

    def test_existing_names_conflict(self, mocker):
        """需求 3.1, 3.2: 已有名称冲突时递增"""
        # 获取第一个提供商的基础名称
        from app.providers import get_all_providers
        import re
        first_type_id = list(get_all_providers().keys())[0]
        first_name = get_all_providers()[first_type_id]['name']
        base = re.sub(r'[^a-zA-Z0-9_-]', '', first_name)
        dialog = self._make_dialog(mocker, existing_names=[f'{base}1', f'{base}2'])
        assert dialog.nameEdit.text() == f'{base}3'
        dialog.close()
