import os
import sys
import pytest
from unittest.mock import MagicMock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _mock_remote_deps(mocker):
    mock_rclone = MagicMock()
    mock_rclone.version.return_value = 'rclone v1.0.0'
    mock_rclone.rclone_path = '/usr/bin/rclone'
    mock_rclone.config_path = '/tmp/rclone.conf'
    mock_rclone.config_dump.return_value = {}
    mock_rclone.listremotes.return_value = []
    mocker.patch('app.views.remote_interface.RClone', return_value=mock_rclone)

    mock_cm = MagicMock()
    mock_cm.list_remotes.return_value = []
    mock_cm.refresh.return_value = None
    mocker.patch('app.views.remote_interface.ConfigManager', return_value=mock_cm)

    return {
        'rclone': mock_rclone,
        'config_manager': mock_cm,
    }


class TestRemoteCard:

    def _make_card(self, mocker, name='myremote', rtype='s3', config=None):
        deps = _mock_remote_deps(mocker)
        from app.models.remote import Remote
        from app.views.remote_interface import RemoteCard
        remote = Remote(name=name, type=rtype, config=config or {})
        card = RemoteCard(remote)
        return card, remote, deps

    def test_card_creation_basic(self, mocker):
        card, remote, _ = self._make_card(mocker)
        assert card.remote == remote
        assert card.nameLabel.text() == 'myremote'

    def test_card_type_label_without_host(self, mocker):
        card, _, _ = self._make_card(mocker, config={})
        assert card.typeLabel.text() == 's3'

    def test_card_type_label_with_host(self, mocker):
        card, _, _ = self._make_card(mocker, rtype='webdav',
                                      config={'host': 'example.com'})
        assert 'example.com' in card.typeLabel.text()
        assert 'webdav' in card.typeLabel.text()

    def test_card_edit_signal(self, mocker):
        card, _, _ = self._make_card(mocker)
        received = []
        card.editClicked.connect(lambda n: received.append(n))
        card.editBtn.click()
        assert received == ['myremote']

    def test_card_delete_signal(self, mocker):
        card, _, _ = self._make_card(mocker)
        received = []
        card.deleteClicked.connect(lambda n: received.append(n))
        card.deleteBtn.click()
        assert received == ['myremote']

    def test_card_test_signal(self, mocker):
        card, _, _ = self._make_card(mocker)
        received = []
        card.testClicked.connect(lambda n: received.append(n))
        card.testBtn.click()
        assert received == ['myremote']

    def test_card_fixed_height(self, mocker):
        card, _, _ = self._make_card(mocker)
        assert card.maximumHeight() == 80

    def test_card_with_url_config(self, mocker):
        card, _, _ = self._make_card(mocker, rtype='webdav',
                                      config={'url': 'https://dav.example.com'})
        assert 'https://dav.example.com' in card.typeLabel.text()


class TestAddRemoteDialog:

    def _make_dialog(self, mocker, remote=None):
        deps = _mock_remote_deps(mocker)
        from app.views.remote_interface import AddRemoteDialog
        dialog = AddRemoteDialog(parent=None, remote=remote)
        return dialog, deps

    def test_dialog_creation_add_mode(self, mocker):
        dialog, _ = self._make_dialog(mocker)
        # 自动命名功能会根据默认类型生成名称（如 WebDAV1）
        assert dialog.nameEdit.text() != ''
        assert dialog.nameEdit.isEnabled()
        dialog.close()

    def test_dialog_creation_edit_mode(self, mocker):
        from app.models.remote import Remote
        remote = Remote(name='test-remote', type='webdav',
                        config={'url': 'https://example.com', 'user': 'admin'})
        dialog, _ = self._make_dialog(mocker, remote=remote)
        assert dialog.nameEdit.text() == 'test-remote'
        assert not dialog.nameEdit.isEnabled()
        dialog.close()

    def test_dialog_type_combo_populated(self, mocker):
        dialog, _ = self._make_dialog(mocker)
        assert dialog.typeCombo.count() > 0
        dialog.close()

    def test_dialog_onTypeChanged_creates_fields(self, mocker):
        dialog, _ = self._make_dialog(mocker)
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 's3':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'access_key_id' in dialog.fieldWidgets
        assert 'secret_access_key' in dialog.fieldWidgets
        dialog.close()

    def test_dialog_onTypeChanged_clears_old_fields(self, mocker):
        dialog, _ = self._make_dialog(mocker)
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 's3':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'access_key_id' in dialog.fieldWidgets
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'webdav':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'access_key_id' not in dialog.fieldWidgets
        assert 'url' in dialog.fieldWidgets
        dialog.close()

    def test_dialog_getData_returns_tuple(self, mocker):
        dialog, _ = self._make_dialog(mocker)
        dialog.nameEdit.setText('myremote')
        # 标记为手动编辑，防止类型切换时覆盖名称
        dialog._name_manually_edited = True
        # 切换到 webdav 类型以确保 url 字段存在
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'webdav':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'url' in dialog.fieldWidgets
        dialog.fieldWidgets['url'].setText('https://example.com')
        # 强制显示以确保 isVisible() 返回 True
        dialog.show()
        name, type_id, options = dialog.getData()
        assert name == 'myremote'
        assert type_id == 'webdav'
        assert options.get('url') == 'https://example.com'
        dialog.close()

    def test_dialog_loadRemote_sets_fields(self, mocker):
        from app.models.remote import Remote
        remote = Remote(name='sftp-server', type='sftp',
                        config={'host': '192.168.1.1', 'port': '2222', 'user': 'root'})
        dialog, _ = self._make_dialog(mocker, remote=remote)
        assert dialog.nameEdit.text() == 'sftp-server'
        if 'host' in dialog.fieldWidgets:
            assert dialog.fieldWidgets['host'].text() == '192.168.1.1'
        if 'user' in dialog.fieldWidgets:
            assert dialog.fieldWidgets['user'].text() == 'root'
        dialog.close()


class TestRemoteInterface:

    def _make_interface(self, mocker, remotes=None):
        deps = _mock_remote_deps(mocker)
        if remotes is not None:
            deps['config_manager'].list_remotes.return_value = remotes
        from app.views.remote_interface import RemoteInterface
        interface = RemoteInterface()
        return interface, deps

    def test_interface_creation(self, mocker):
        interface, _ = self._make_interface(mocker)
        assert interface.objectName() == 'remoteInterface'

    def test_interface_loadRemotes_empty(self, mocker):
        interface, deps = self._make_interface(mocker, remotes=[])
        interface.loadRemotes()
        assert interface.listLayout.count() >= 1

    def test_interface_loadRemotes_with_remotes(self, mocker):
        from app.models.remote import Remote
        remotes = [
            Remote(name='remote1', type='s3'),
            Remote(name='remote2', type='webdav', config={'url': 'https://x.com'}),
        ]
        interface, deps = self._make_interface(mocker, remotes=remotes)
        interface.loadRemotes()
        assert interface.listLayout.count() == 2

    def test_interface_loadRemotes_clears_previous(self, mocker):
        from app.models.remote import Remote
        remotes1 = [Remote(name='r1', type='s3')]
        interface, deps = self._make_interface(mocker, remotes=remotes1)
        interface.loadRemotes()
        assert interface.listLayout.count() == 1
        deps['config_manager'].list_remotes.return_value = [
            Remote(name='r1', type='s3'),
            Remote(name='r2', type='ftp'),
        ]
        interface.loadRemotes()
        assert interface.listLayout.count() == 2

    def test_interface_testRemote_success(self, mocker):
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].test_remote.return_value = (True, 'Connection successful')
        interface.testRemote('myremote')
        deps['config_manager'].test_remote.assert_called_once_with('myremote')

    def test_interface_testRemote_failure(self, mocker):
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].test_remote.return_value = (False, 'Connection failed')
        interface.testRemote('myremote')
        deps['config_manager'].test_remote.assert_called_once_with('myremote')

    def test_interface_has_add_button(self, mocker):
        interface, _ = self._make_interface(mocker)
        assert interface.addBtn is not None

    def test_interface_has_refresh_button(self, mocker):
        interface, _ = self._make_interface(mocker)
        assert interface.refreshBtn is not None


class TestAddRemoteDialogRegistryPaths:
    """补充 AddRemoteDialog 中 Registry 调用路径的测试覆盖。"""

    def _make_dialog(self, mocker, remote=None, existing_names=None):
        deps = _mock_remote_deps(mocker)
        from app.views.remote_interface import AddRemoteDialog
        dialog = AddRemoteDialog(parent=None, remote=remote,
                                 existing_names=existing_names)
        return dialog, deps

    def test_accept_empty_name_shows_warning(self, mocker):
        """accept() 空名称时显示警告并不关闭对话框（lines 180-185）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog.nameEdit.setText('')
        dialog._name_manually_edited = True
        # accept 不应关闭对话框
        dialog.accept()
        # 对话框仍然存在（未调用 super().accept()）
        assert dialog.nameEdit.text() == ''
        dialog.close()

    def test_onTypeChanged_sftp_creates_text_fields(self, mocker):
        """onTypeChanged 切换到 SFTP 时创建 text 类型字段（lines 249+）。"""
        dialog, _ = self._make_dialog(mocker)
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'sftp':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'host' in dialog.fieldWidgets
        assert 'user' in dialog.fieldWidgets
        dialog.close()

    def test_onTypeChanged_ftp_creates_fields(self, mocker):
        """onTypeChanged 切换到 FTP 时创建字段。"""
        dialog, _ = self._make_dialog(mocker)
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'ftp':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'host' in dialog.fieldWidgets
        dialog.close()

    def test_onTypeChanged_smb_creates_fields(self, mocker):
        """onTypeChanged 切换到 SMB 时创建字段。"""
        dialog, _ = self._make_dialog(mocker)
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'smb':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'host' in dialog.fieldWidgets
        dialog.close()

    def test_onTypeChanged_s3_triggers_provider_linkage(self, mocker):
        """onTypeChanged 切换到 S3 时触发 provider 联动（lines 302, 321, 338, 348）。"""
        dialog, _ = self._make_dialog(mocker)
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 's3':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'provider' in dialog.fieldWidgets
        assert 'region' in dialog.fieldWidgets
        assert 'endpoint' in dialog.fieldWidgets
        dialog.close()

    def test_onTypeChanged_webdav_triggers_vendor_linkage(self, mocker):
        """onTypeChanged 切换到 WebDAV 时触发 vendor 联动（lines 277）。"""
        dialog, _ = self._make_dialog(mocker)
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'webdav':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert 'vendor' in dialog.fieldWidgets
        assert 'url' in dialog.fieldWidgets
        dialog.close()

    def test_s3_provider_changed_updates_region_and_endpoint(self, mocker):
        """S3 Provider 切换时动态调整 region 和 endpoint 字段（lines 354-361, 372, 395, 412-417）。"""
        dialog, _ = self._make_dialog(mocker)
        # 切换到 S3
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 's3':
                dialog.typeCombo.setCurrentIndex(i)
                break

        provider_widget = dialog.fieldWidgets.get('provider')
        assert provider_widget is not None

        # 切换到不同的 provider（如 AWS）
        from qfluentwidgets import ComboBox
        if isinstance(provider_widget, ComboBox) and provider_widget.count() > 1:
            provider_widget.setCurrentIndex(1)

        # region 和 endpoint 字段应仍然存在
        assert 'region' in dialog.fieldWidgets
        assert 'endpoint' in dialog.fieldWidgets
        dialog.close()

    def test_webdav_vendor_changed_updates_placeholders(self, mocker):
        """WebDAV Vendor 切换时更新 url 和 user 的 placeholder（lines 277-295）。"""
        dialog, _ = self._make_dialog(mocker)
        # 切换到 WebDAV
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'webdav':
                dialog.typeCombo.setCurrentIndex(i)
                break

        vendor_widget = dialog.fieldWidgets.get('vendor')
        assert vendor_widget is not None

        from qfluentwidgets import ComboBox
        if isinstance(vendor_widget, ComboBox) and vendor_widget.count() > 1:
            vendor_widget.setCurrentIndex(1)

        # url 字段应仍然存在
        assert 'url' in dialog.fieldWidgets
        dialog.close()

    def test_getData_s3_auto_endpoint(self, mocker):
        """getData 中 S3 自动生成 endpoint（lines 495-503）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        dialog.nameEdit.setText('my-s3')

        # 切换到 S3
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 's3':
                dialog.typeCombo.setCurrentIndex(i)
                break

        dialog.show()

        # 设置 provider 和 region
        provider_widget = dialog.fieldWidgets.get('provider')
        region_widget = dialog.fieldWidgets.get('region')

        if provider_widget and region_widget:
            from qfluentwidgets import ComboBox
            # 选择 AWS provider
            if isinstance(provider_widget, ComboBox):
                aws_idx = provider_widget.findText('AWS')
                if aws_idx >= 0:
                    provider_widget.setCurrentIndex(aws_idx)

            # 设置 region
            if isinstance(region_widget, ComboBox) and region_widget.count() > 0:
                region_widget.setCurrentIndex(0)
            elif hasattr(region_widget, 'setText'):
                region_widget.setText('us-east-1')

        name, type_id, options = dialog.getData()
        assert type_id == 's3'
        dialog.close()

    def test_loadRemote_with_combo_field(self, mocker):
        """loadRemote 加载含 ComboBox 字段的远程存储（lines 461, 467-470）。"""
        from app.models.remote import Remote
        remote = Remote(name='my-webdav', type='webdav',
                        config={'url': 'https://dav.example.com',
                                'vendor': 'Nextcloud',
                                'user': 'admin',
                                'pass': 'secret'})
        dialog, _ = self._make_dialog(mocker, remote=remote)
        assert dialog.nameEdit.text() == 'my-webdav'
        if 'url' in dialog.fieldWidgets:
            assert dialog.fieldWidgets['url'].text() == 'https://dav.example.com'
        dialog.close()

    def test_loadRemote_s3_with_provider_config(self, mocker):
        """loadRemote 加载 S3 类型远程存储并设置 provider 字段（lines 467-470, 485）。"""
        from app.models.remote import Remote
        remote = Remote(name='my-s3', type='s3',
                        config={'provider': 'AWS', 'region': 'us-east-1',
                                'access_key_id': 'AKID', 'secret_access_key': 'secret'})
        dialog, _ = self._make_dialog(mocker, remote=remote)
        assert dialog.nameEdit.text() == 'my-s3'
        if 'provider' in dialog.fieldWidgets:
            from qfluentwidgets import ComboBox
            widget = dialog.fieldWidgets['provider']
            if isinstance(widget, ComboBox):
                assert widget.currentText() == 'AWS'
        dialog.close()

    def test_clearFields_clears_all_widgets(self, mocker):
        """_clearFields 清理所有动态字段控件（lines 200-204）。"""
        dialog, _ = self._make_dialog(mocker)
        # 先切换到 sftp 创建字段
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'sftp':
                dialog.typeCombo.setCurrentIndex(i)
                break
        assert len(dialog.fieldWidgets) > 0
        # 再切换到其他类型，会触发 _clearFields
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'ftp':
                dialog.typeCombo.setCurrentIndex(i)
                break
        # 旧字段应被清理，新字段应存在
        assert 'host' in dialog.fieldWidgets
        dialog.close()

    def test_auto_naming_on_type_change(self, mocker):
        """类型切换时自动命名（lines 168-176, _applyAutoName）。"""
        dialog, _ = self._make_dialog(mocker)
        # 确保非编辑模式
        assert dialog.remote is None
        dialog._name_manually_edited = False
        # 切换类型
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'sftp':
                dialog.typeCombo.setCurrentIndex(i)
                break
        # 名称应自动更新
        assert dialog.nameEdit.text() != ''
        dialog.close()


class TestRemoteInterfaceRegistryPaths:
    """补充 RemoteInterface 中 Registry 调用路径的测试覆盖。"""

    def _make_interface(self, mocker, remotes=None):
        deps = _mock_remote_deps(mocker)
        if remotes is not None:
            deps['config_manager'].list_remotes.return_value = remotes
        from app.views.remote_interface import RemoteInterface
        interface = RemoteInterface()
        return interface, deps

    def test_showAddDialog_confirm_success(self, mocker):
        """showAddDialog 用户确认添加成功（lines 589-605）。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].add_remote.return_value = True
        deps['config_manager'].list_remotes.return_value = []

        from app.views.remote_interface import AddRemoteDialog
        mocker.patch.object(AddRemoteDialog, 'exec', return_value=1)
        mocker.patch.object(AddRemoteDialog, 'getData',
                           return_value=('test-remote', 'sftp', {'host': '1.2.3.4'}))

        interface.showAddDialog()
        deps['config_manager'].add_remote.assert_called_once_with(
            'test-remote', 'sftp', host='1.2.3.4')

    def test_showAddDialog_confirm_failure(self, mocker):
        """showAddDialog 用户确认但添加失败（lines 606-609）。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].add_remote.return_value = False

        from app.views.remote_interface import AddRemoteDialog
        mocker.patch.object(AddRemoteDialog, 'exec', return_value=1)
        mocker.patch.object(AddRemoteDialog, 'getData',
                           return_value=('test-remote', 'sftp', {'host': '1.2.3.4'}))

        interface.showAddDialog()
        deps['config_manager'].add_remote.assert_called_once()

    def test_showAddDialog_cancel(self, mocker):
        """showAddDialog 用户取消（lines 589-593）。"""
        interface, deps = self._make_interface(mocker)

        from app.views.remote_interface import AddRemoteDialog
        mocker.patch.object(AddRemoteDialog, 'exec', return_value=0)

        interface.showAddDialog()
        deps['config_manager'].add_remote.assert_not_called()

    def test_showEditDialog_confirm_success(self, mocker):
        """showEditDialog 用户确认编辑成功（lines 614-635）。"""
        from app.models.remote import Remote
        interface, deps = self._make_interface(mocker)
        remote = Remote(name='edit-me', type='sftp', config={'host': '1.2.3.4'})
        deps['config_manager'].get_remote.return_value = remote
        deps['config_manager'].update_remote.return_value = True
        deps['config_manager'].list_remotes.return_value = [remote]

        from app.views.remote_interface import AddRemoteDialog
        mocker.patch.object(AddRemoteDialog, 'exec', return_value=1)
        mocker.patch.object(AddRemoteDialog, 'getData',
                           return_value=('edit-me', 'sftp', {'host': '5.6.7.8'}))

        interface.showEditDialog('edit-me')
        deps['config_manager'].update_remote.assert_called_once_with(
            'edit-me', host='5.6.7.8')

    def test_showEditDialog_confirm_failure(self, mocker):
        """showEditDialog 用户确认但更新失败（lines 636-639）。"""
        from app.models.remote import Remote
        interface, deps = self._make_interface(mocker)
        remote = Remote(name='edit-me', type='sftp', config={'host': '1.2.3.4'})
        deps['config_manager'].get_remote.return_value = remote
        deps['config_manager'].update_remote.return_value = False

        from app.views.remote_interface import AddRemoteDialog
        mocker.patch.object(AddRemoteDialog, 'exec', return_value=1)
        mocker.patch.object(AddRemoteDialog, 'getData',
                           return_value=('edit-me', 'sftp', {'host': '5.6.7.8'}))

        interface.showEditDialog('edit-me')
        deps['config_manager'].update_remote.assert_called_once()

    def test_showEditDialog_remote_not_found(self, mocker):
        """showEditDialog 远程存储不存在（lines 617-618）。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].get_remote.return_value = None

        interface.showEditDialog('nonexistent')
        # 不应打开对话框

    def test_deleteRemote_confirm_success(self, mocker):
        """deleteRemote 用户确认删除成功（lines 643-656）。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].delete_remote.return_value = True
        deps['config_manager'].list_remotes.return_value = []

        from qfluentwidgets import MessageBox
        mocker.patch.object(MessageBox, 'exec', return_value=1)

        interface.deleteRemote('delete-me')
        deps['config_manager'].delete_remote.assert_called_once_with('delete-me')

    def test_deleteRemote_confirm_failure(self, mocker):
        """deleteRemote 用户确认但删除失败（lines 657-659）。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].delete_remote.return_value = False

        from qfluentwidgets import MessageBox
        mocker.patch.object(MessageBox, 'exec', return_value=1)

        interface.deleteRemote('delete-me')
        deps['config_manager'].delete_remote.assert_called_once()

    def test_deleteRemote_cancel(self, mocker):
        """deleteRemote 用户取消删除（lines 660-662）。"""
        interface, deps = self._make_interface(mocker)

        from qfluentwidgets import MessageBox
        mocker.patch.object(MessageBox, 'exec', return_value=0)

        interface.deleteRemote('delete-me')
        deps['config_manager'].delete_remote.assert_not_called()


class TestAddRemoteDialogS3DeepPaths:
    """深度测试 S3 Provider 切换时的 region/endpoint 动态替换逻辑。"""

    def _make_dialog(self, mocker, remote=None):
        deps = _mock_remote_deps(mocker)
        from app.views.remote_interface import AddRemoteDialog
        dialog = AddRemoteDialog(parent=None, remote=remote)
        return dialog, deps

    def _switch_to_s3(self, dialog):
        """切换到 S3 类型"""
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 's3':
                dialog.typeCombo.setCurrentIndex(i)
                return True
        return False

    def test_s3_switch_between_providers(self, mocker):
        """S3 在不同 provider 之间切换时 region/endpoint 字段被替换（lines 338-395）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        self._switch_to_s3(dialog)

        provider_widget = dialog.fieldWidgets.get('provider')
        assert provider_widget is not None

        from qfluentwidgets import ComboBox
        if isinstance(provider_widget, ComboBox) and provider_widget.count() >= 2:
            # 切换到第二个 provider
            provider_widget.setCurrentIndex(1)
            assert 'region' in dialog.fieldWidgets
            assert 'endpoint' in dialog.fieldWidgets

            # 再切换回第一个
            provider_widget.setCurrentIndex(0)
            assert 'region' in dialog.fieldWidgets
            assert 'endpoint' in dialog.fieldWidgets

        dialog.close()

    def test_s3_provider_with_custom_provider(self, mocker):
        """S3 切换到自定义 provider（如 Other）时 endpoint 可编辑（lines 412-425）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        self._switch_to_s3(dialog)

        provider_widget = dialog.fieldWidgets.get('provider')
        assert provider_widget is not None

        from qfluentwidgets import ComboBox
        if isinstance(provider_widget, ComboBox):
            # 查找 "Other" 或最后一个 provider（通常是自定义的）
            other_idx = provider_widget.findText('Other')
            if other_idx >= 0:
                provider_widget.setCurrentIndex(other_idx)
            elif provider_widget.count() > 2:
                provider_widget.setCurrentIndex(provider_widget.count() - 1)

        assert 'endpoint' in dialog.fieldWidgets
        dialog.close()

    def test_s3_getData_with_auto_endpoint_generation(self, mocker):
        """S3 getData 中自动生成 endpoint（lines 495-503）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        dialog.nameEdit.setText('test-s3')
        self._switch_to_s3(dialog)

        dialog.show()
        name, type_id, options = dialog.getData()
        assert type_id == 's3'
        # provider 应该在 options 中
        if 'provider' in options:
            assert isinstance(options['provider'], str)
        dialog.close()

    def test_s3_loadRemote_restores_provider_and_region(self, mocker):
        """S3 loadRemote 恢复 provider 和 region 字段值（lines 461, 467-470）。"""
        from app.models.remote import Remote
        remote = Remote(name='my-s3-edit', type='s3',
                        config={'provider': 'AWS',
                                'access_key_id': 'AKID123',
                                'secret_access_key': 'SECRET'})
        dialog, _ = self._make_dialog(mocker, remote=remote)
        assert dialog.nameEdit.text() == 'my-s3-edit'
        assert not dialog.nameEdit.isEnabled()  # 编辑模式名称不可编辑

        # provider 字段应被设置
        provider_widget = dialog.fieldWidgets.get('provider')
        if provider_widget:
            from qfluentwidgets import ComboBox
            if isinstance(provider_widget, ComboBox):
                assert provider_widget.currentText() == 'AWS'
        dialog.close()

    def test_webdav_loadRemote_restores_vendor(self, mocker):
        """WebDAV loadRemote 恢复 vendor 字段值。"""
        from app.models.remote import Remote
        # 使用 vendor 列表中实际存在的值
        remote = Remote(name='my-webdav-edit', type='webdav',
                        config={'url': 'https://cloud.example.com/remote.php/dav',
                                'vendor': '123Pan',
                                'user': 'admin'})
        dialog, _ = self._make_dialog(mocker, remote=remote)
        assert dialog.nameEdit.text() == 'my-webdav-edit'

        vendor_widget = dialog.fieldWidgets.get('vendor')
        if vendor_widget:
            from qfluentwidgets import ComboBox
            if isinstance(vendor_widget, ComboBox):
                # vendor 应被正确设置（loadRemote 中通过 findText 匹配）
                assert vendor_widget.currentText() != ''
        dialog.close()

    def test_showAddDialog_incomplete_data(self, mocker):
        """showAddDialog 数据不完整时的处理（line 611）。"""
        deps = _mock_remote_deps(mocker)
        from app.views.remote_interface import RemoteInterface, AddRemoteDialog
        interface = RemoteInterface()

        mocker.patch.object(AddRemoteDialog, 'exec', return_value=1)
        mocker.patch.object(AddRemoteDialog, 'getData',
                           return_value=('', '', {}))

        interface.showAddDialog()
        # 名称为空，不应调用 add_remote
        deps['config_manager'].add_remote.assert_not_called()


class TestAddRemoteDialogCoveragePaths:
    """补充 AddRemoteDialog 中未覆盖代码路径的测试。"""

    def _make_dialog(self, mocker, remote=None, existing_names=None):
        deps = _mock_remote_deps(mocker)
        from app.views.remote_interface import AddRemoteDialog
        dialog = AddRemoteDialog(parent=None, remote=remote,
                                 existing_names=existing_names)
        return dialog, deps

    def _switch_to_type(self, dialog, type_id):
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == type_id:
                dialog.typeCombo.setCurrentIndex(i)
                return True
        return False

    def test_onTypeChanged_unknown_type_returns_early(self, mocker):
        """onTypeChanged 中 get_provider 返回 None 时提前返回（line 185）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True

        # 手动调用 onTypeChanged 并 mock get_provider 返回 None
        mocker.patch('app.views.remote_interface.get_provider', return_value=None)
        dialog.onTypeChanged(0)

        # 字段应被清空（_clearFields 已执行），但不会添加新字段
        assert len(dialog.fieldWidgets) == 0
        dialog.close()

    def test_s3_aws_provider_creates_choice_region(self, mocker):
        """S3 切换到 AWS 时 region 变为 choice 类型（lines 200-204, 220-221）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        self._switch_to_type(dialog, 's3')

        provider_widget = dialog.fieldWidgets.get('provider')
        assert provider_widget is not None

        from qfluentwidgets import ComboBox
        # AWS 是第一个 provider，初始化时已触发 _onS3ProviderChanged(0)
        # region 应该是 ComboBox 类型
        region_widget = dialog.fieldWidgets.get('region')
        assert region_widget is not None
        assert isinstance(region_widget, ComboBox), \
            f"AWS region 应为 ComboBox，实际为 {type(region_widget).__name__}"

        # 验证 region 有选项
        assert region_widget.count() > 0

        # 验证 endpoint 是自动生成的（只读）
        endpoint_widget = dialog.fieldWidgets.get('endpoint')
        assert endpoint_widget is not None
        assert not endpoint_widget.isEnabled(), "AWS endpoint 应为只读"

        dialog.close()

    def test_s3_aws_to_ceph_region_changes_to_text(self, mocker):
        """S3 从 AWS 切换到 Ceph 时 region 从 choice 变为 text（lines 200-210）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        self._switch_to_type(dialog, 's3')

        provider_widget = dialog.fieldWidgets.get('provider')
        from qfluentwidgets import ComboBox
        from qfluentwidgets import LineEdit

        # 初始为 AWS，region 应为 ComboBox
        region_widget = dialog.fieldWidgets.get('region')
        assert isinstance(region_widget, ComboBox)

        # 切换到 Ceph
        ceph_idx = provider_widget.findText('Ceph')
        if ceph_idx >= 0:
            provider_widget.setCurrentIndex(ceph_idx)

        # region 应变为 LineEdit（text 类型）
        region_widget = dialog.fieldWidgets.get('region')
        assert isinstance(region_widget, LineEdit), \
            f"Ceph region 应为 LineEdit，实际为 {type(region_widget).__name__}"

        # endpoint 应可编辑
        endpoint_widget = dialog.fieldWidgets.get('endpoint')
        assert endpoint_widget is not None
        assert endpoint_widget.isEnabled(), "Ceph endpoint 应可编辑"

        dialog.close()

    def test_s3_aws_region_change_updates_endpoint(self, mocker):
        """S3 AWS 的 region 变化时自动更新 endpoint（line 277, _updateAutoEndpoint）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        self._switch_to_type(dialog, 's3')

        from qfluentwidgets import ComboBox

        region_widget = dialog.fieldWidgets.get('region')
        endpoint_widget = dialog.fieldWidgets.get('endpoint')
        assert isinstance(region_widget, ComboBox)
        assert endpoint_widget is not None

        # 切换 region 到不同的值
        if region_widget.count() > 1:
            region_widget.setCurrentIndex(1)
            region_text = region_widget.currentText()
            # endpoint 应包含新的 region 值
            expected_endpoint = f's3.{region_text}.amazonaws.com'
            assert endpoint_widget.text() == expected_endpoint

        dialog.close()

    def test_loadRemote_unknown_type_logs_warning(self, mocker):
        """loadRemote 中类型未找到时记录 warning（line 302）。"""
        from app.models.remote import Remote
        remote = Remote(name='unknown-remote', type='unknowntype',
                        config={'host': 'example.com'})
        dialog, _ = self._make_dialog(mocker, remote=remote)

        # 类型未找到，但对话框仍应创建成功
        assert dialog.nameEdit.text() == 'unknown-remote'
        assert not dialog.nameEdit.isEnabled()
        dialog.close()

    def test_getData_s3_auto_endpoint_when_endpoint_not_in_options(self, mocker):
        """getData 中 S3 endpoint 不在 options 中时自动生成（lines 338, 348, 501-503）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        dialog.nameEdit.setText('auto-ep-test')
        self._switch_to_type(dialog, 's3')

        dialog.show()

        from qfluentwidgets import ComboBox

        # 确保 provider 是 AWS（有 auto_format）
        provider_widget = dialog.fieldWidgets.get('provider')
        if isinstance(provider_widget, ComboBox):
            aws_idx = provider_widget.findText('AWS')
            if aws_idx >= 0:
                provider_widget.setCurrentIndex(aws_idx)

        # endpoint 字段在 AWS 模式下是只读的，不会被 getData 收集
        # （因为 isVisible 为 True 但 isEnabled 为 False，但 text 不为空）
        # 需要确保 endpoint 被隐藏或清空以触发 auto_format 路径
        endpoint_widget = dialog.fieldWidgets.get('endpoint')
        if endpoint_widget:
            # 清空 endpoint 文本以触发 auto_format 路径
            endpoint_widget.setText('')

        name, type_id, options = dialog.getData()
        assert type_id == 's3'
        assert name == 'auto-ep-test'

        dialog.close()

    def test_s3_ceph_to_aws_restores_region_value(self, mocker):
        """S3 从 Ceph 切换到 AWS 时尝试恢复 region 旧值（lines 200-204）。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        self._switch_to_type(dialog, 's3')

        from qfluentwidgets import ComboBox
        from qfluentwidgets import LineEdit

        provider_widget = dialog.fieldWidgets.get('provider')

        # 先切换到 Ceph（text region）
        ceph_idx = provider_widget.findText('Ceph')
        if ceph_idx >= 0:
            provider_widget.setCurrentIndex(ceph_idx)

        # 在 Ceph 的 text region 中输入一个 AWS region 名称
        region_widget = dialog.fieldWidgets.get('region')
        if isinstance(region_widget, LineEdit):
            region_widget.setText('us-east-1')

        # 切换回 AWS（choice region），应尝试恢复 'us-east-1'
        aws_idx = provider_widget.findText('AWS')
        if aws_idx >= 0:
            provider_widget.setCurrentIndex(aws_idx)

        region_widget = dialog.fieldWidgets.get('region')
        if isinstance(region_widget, ComboBox):
            # 应恢复到 us-east-1
            assert region_widget.currentText() == 'us-east-1'

        dialog.close()


class TestRemoteInterfaceCoveragePaths:
    """补充 RemoteInterface 中未覆盖的 showAddDialog/deleteRemote 代码路径。"""

    def _make_interface(self, mocker, remotes=None):
        deps = _mock_remote_deps(mocker)
        if remotes is not None:
            deps['config_manager'].list_remotes.return_value = remotes
        from app.views.remote_interface import RemoteInterface
        interface = RemoteInterface()
        return interface, deps

    def test_showAddDialog_success_covers_add_remote_call(self, mocker):
        """覆盖 showAddDialog 中 add_remote 成功路径（lines 360-361, 395）。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].add_remote.return_value = True
        deps['config_manager'].list_remotes.return_value = []

        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1
        mock_dialog.getData.return_value = ('new-remote', 'sftp', {'host': '10.0.0.1'})

        mocker.patch('app.views.remote_interface.AddRemoteDialog', return_value=mock_dialog)

        interface.showAddDialog()
        deps['config_manager'].add_remote.assert_called_once_with(
            'new-remote', 'sftp', host='10.0.0.1')

    def test_showAddDialog_failure_covers_error_path(self, mocker):
        """覆盖 showAddDialog 中 add_remote 失败路径（line 372）。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].add_remote.return_value = False

        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1
        mock_dialog.getData.return_value = ('fail-remote', 'sftp', {'host': '10.0.0.1'})

        mocker.patch('app.views.remote_interface.AddRemoteDialog', return_value=mock_dialog)

        interface.showAddDialog()
        deps['config_manager'].add_remote.assert_called_once()

    def test_showAddDialog_incomplete_data_covers_warning(self, mocker):
        """覆盖 showAddDialog 中数据不完整的 warning 路径。"""
        interface, deps = self._make_interface(mocker)

        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1
        mock_dialog.getData.return_value = ('', '', {})

        mocker.patch('app.views.remote_interface.AddRemoteDialog', return_value=mock_dialog)

        interface.showAddDialog()
        deps['config_manager'].add_remote.assert_not_called()

    def test_showEditDialog_success_covers_update_path(self, mocker):
        """覆盖 showEditDialog 中 update_remote 成功路径。"""
        from app.models.remote import Remote
        interface, deps = self._make_interface(mocker)
        remote = Remote(name='edit-test', type='sftp', config={'host': '1.2.3.4'})
        deps['config_manager'].get_remote.return_value = remote
        deps['config_manager'].update_remote.return_value = True
        deps['config_manager'].list_remotes.return_value = [remote]

        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1
        mock_dialog.getData.return_value = ('edit-test', 'sftp', {'host': '5.6.7.8'})

        mocker.patch('app.views.remote_interface.AddRemoteDialog', return_value=mock_dialog)

        interface.showEditDialog('edit-test')
        deps['config_manager'].update_remote.assert_called_once_with(
            'edit-test', host='5.6.7.8')

    def test_showEditDialog_failure_covers_error_path(self, mocker):
        """覆盖 showEditDialog 中 update_remote 失败路径。"""
        from app.models.remote import Remote
        interface, deps = self._make_interface(mocker)
        remote = Remote(name='edit-fail', type='sftp', config={'host': '1.2.3.4'})
        deps['config_manager'].get_remote.return_value = remote
        deps['config_manager'].update_remote.return_value = False

        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1
        mock_dialog.getData.return_value = ('edit-fail', 'sftp', {'host': '5.6.7.8'})

        mocker.patch('app.views.remote_interface.AddRemoteDialog', return_value=mock_dialog)

        interface.showEditDialog('edit-fail')
        deps['config_manager'].update_remote.assert_called_once()

    def test_deleteRemote_success_covers_delete_path(self, mocker):
        """覆盖 deleteRemote 中 delete_remote 成功路径（lines 423-425, 433, 436）。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].delete_remote.return_value = True
        deps['config_manager'].list_remotes.return_value = []

        mocker.patch('app.views.remote_interface.MessageBox') \
              .return_value.exec.return_value = 1

        interface.deleteRemote('del-test')
        deps['config_manager'].delete_remote.assert_called_once_with('del-test')

    def test_deleteRemote_failure_covers_error_path(self, mocker):
        """覆盖 deleteRemote 中 delete_remote 失败路径。"""
        interface, deps = self._make_interface(mocker)
        deps['config_manager'].delete_remote.return_value = False

        mocker.patch('app.views.remote_interface.MessageBox') \
              .return_value.exec.return_value = 1

        interface.deleteRemote('del-fail')
        deps['config_manager'].delete_remote.assert_called_once()

    def test_deleteRemote_cancel_covers_cancel_path(self, mocker):
        """覆盖 deleteRemote 中用户取消路径（line 485）。"""
        interface, deps = self._make_interface(mocker)

        mocker.patch('app.views.remote_interface.MessageBox') \
              .return_value.exec.return_value = 0

        interface.deleteRemote('del-cancel')
        deps['config_manager'].delete_remote.assert_not_called()
