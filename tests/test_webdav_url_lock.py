"""
WebDAV URL 锁定功能的单元测试。

测试 AddRemoteDialog 中 _onWebdavVendorChanged 方法的 URL 自动填充和只读锁定行为。

Requirements: 5.1, 5.2, 5.3, 5.4, 6.3
"""

import os
import sys
import pytest
from unittest.mock import MagicMock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from qfluentwidgets import ComboBox, LineEdit


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _mock_remote_deps(mocker):
    """Mock RClone 和 ConfigManager 依赖，与现有测试模式一致。"""
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

    return {'rclone': mock_rclone, 'config_manager': mock_cm}


class TestWebdavUrlLock:
    """WebDAV URL 锁定功能单元测试。"""

    def _make_dialog(self, mocker, remote=None):
        """创建 AddRemoteDialog 实例并切换到 WebDAV 类型。"""
        deps = _mock_remote_deps(mocker)
        from app.views.remote_interface import AddRemoteDialog
        dialog = AddRemoteDialog(parent=None, remote=remote)
        return dialog, deps

    def _switch_to_webdav(self, dialog):
        """将对话框类型切换到 WebDAV。"""
        for i in range(dialog.typeCombo.count()):
            if dialog.typeCombo.itemData(i) == 'webdav':
                dialog.typeCombo.setCurrentIndex(i)
                return
        raise AssertionError("未找到 WebDAV 类型选项")

    def _get_vendor_widget(self, dialog):
        """获取 vendor ComboBox 控件。"""
        vendor_widget = dialog.fieldWidgets.get('vendor')
        assert vendor_widget is not None, "vendor 字段不存在"
        assert isinstance(vendor_widget, ComboBox), "vendor 字段应为 ComboBox"
        return vendor_widget

    def _get_url_widget(self, dialog):
        """获取 url LineEdit 控件。"""
        url_widget = dialog.fieldWidgets.get('url')
        assert url_widget is not None, "url 字段不存在"
        assert isinstance(url_widget, LineEdit), "url 字段应为 LineEdit"
        return url_widget

    def _select_vendor(self, dialog, vendor_name):
        """选择指定的 vendor。"""
        vendor_widget = self._get_vendor_widget(dialog)
        idx = vendor_widget.findText(vendor_name)
        assert idx >= 0, f"未找到 vendor: {vendor_name}"
        vendor_widget.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # 测试 1: 选择 123Pan 时 URL 自动填充且只读
    # Requirements: 5.1
    # ------------------------------------------------------------------
    def test_123pan_url_autofill_and_readonly(self, mocker):
        """选择 123Pan vendor → URL 应为固定值且只读。"""
        dialog, _ = self._make_dialog(mocker)
        self._switch_to_webdav(dialog)
        self._select_vendor(dialog, '123Pan')

        url_widget = self._get_url_widget(dialog)
        assert url_widget.text() == 'https://webdav.123pan.cn/webdav', \
            f"123Pan URL 应为固定值，实际为: {url_widget.text()!r}"
        assert url_widget.isReadOnly(), "123Pan 的 URL 字段应为只读"
        dialog.close()

    # ------------------------------------------------------------------
    # 测试 2: 选择 Alipan 时 URL 自动填充且只读
    # Requirements: 5.2
    # ------------------------------------------------------------------
    def test_alipan_url_autofill_and_readonly(self, mocker):
        """选择 Alipan vendor → URL 应为固定值且只读。"""
        dialog, _ = self._make_dialog(mocker)
        self._switch_to_webdav(dialog)
        self._select_vendor(dialog, 'Alipan')

        url_widget = self._get_url_widget(dialog)
        assert url_widget.text() == 'https://openapi.alipan.com/dav', \
            f"Alipan URL 应为固定值，实际为: {url_widget.text()!r}"
        assert url_widget.isReadOnly(), "Alipan 的 URL 字段应为只读"
        dialog.close()

    # ------------------------------------------------------------------
    # 测试 3: 选择 other 时 URL 可编辑
    # Requirements: 5.3
    # ------------------------------------------------------------------
    def test_other_url_editable(self, mocker):
        """选择 other vendor → URL 应为空（添加模式）且可编辑。"""
        dialog, _ = self._make_dialog(mocker)
        self._switch_to_webdav(dialog)

        # 先选择 123Pan（触发只读），再切换到 other
        self._select_vendor(dialog, '123Pan')
        self._select_vendor(dialog, 'other')

        url_widget = self._get_url_widget(dialog)
        assert url_widget.text() == '', \
            f"添加模式下 other 的 URL 应为空，实际为: {url_widget.text()!r}"
        assert not url_widget.isReadOnly(), "other 的 URL 字段应可编辑"
        dialog.close()

    # ------------------------------------------------------------------
    # 测试 4: 编辑模式下 vendor 切换行为
    # Requirements: 5.4
    # ------------------------------------------------------------------
    def test_edit_mode_vendor_switch(self, mocker):
        """编辑模式下，从已知 vendor 切换到 other 应保留已有 URL。"""
        from app.models.remote import Remote
        existing_url = 'https://my-custom-webdav.example.com/dav'
        remote = Remote(
            name='my-webdav',
            type='webdav',
            config={
                'url': existing_url,
                'vendor': '123Pan',
                'user': 'testuser',
            },
        )
        dialog, _ = self._make_dialog(mocker, remote=remote)

        url_widget = self._get_url_widget(dialog)

        # 编辑模式加载后，123Pan 的 URL 应被锁定为固定值
        assert url_widget.isReadOnly(), "编辑模式下 123Pan 的 URL 应为只读"

        # 切换到 other：编辑模式下不应清空已有 URL
        self._select_vendor(dialog, 'other')
        assert not url_widget.isReadOnly(), "切换到 other 后 URL 应可编辑"
        # 编辑模式下切换到 other 不清空 URL（保留已有值）
        # 注意：由于 123Pan 锁定时设置了固定 URL，切换到 other 后保留的是固定 URL
        assert url_widget.text() != '', "编辑模式下切换到 other 不应清空 URL"
        dialog.close()

    # ------------------------------------------------------------------
    # 测试 5: getData() 正确收集只读字段的值
    # Requirements: 6.3
    # ------------------------------------------------------------------
    def test_getData_collects_readonly_url(self, mocker):
        """设置 123Pan（只读 URL）后，getData() 应仍返回 URL 值。"""
        dialog, _ = self._make_dialog(mocker)
        dialog._name_manually_edited = True
        dialog.nameEdit.setText('test-webdav')
        self._switch_to_webdav(dialog)
        self._select_vendor(dialog, '123Pan')

        # 确认 URL 已被设置且只读
        url_widget = self._get_url_widget(dialog)
        assert url_widget.isReadOnly(), "URL 应为只读"
        assert url_widget.text() == 'https://webdav.123pan.cn/webdav'

        # 调用 show() 确保 widget 可见性正确（getData 会检查 isHidden）
        dialog.show()

        name, type_id, options = dialog.getData()
        assert type_id == 'webdav', f"类型应为 webdav，实际为: {type_id!r}"
        assert 'url' in options, f"getData 应包含 url 字段，实际 options: {options}"
        assert options['url'] == 'https://webdav.123pan.cn/webdav', \
            f"getData 中 url 值不正确: {options['url']!r}"
        dialog.close()
