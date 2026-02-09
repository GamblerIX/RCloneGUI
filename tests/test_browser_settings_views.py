
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QTreeWidgetItem
from PySide6.QtCore import Qt


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@dataclass
class FakeRCloneResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0


def _make_browser_mocks(mocker):
    mock_rclone = MagicMock()
    mock_rclone.lsjson.return_value = (True, [])
    mock_rclone.version.return_value = "rclone v1.68.0"

    mock_cm = MagicMock()
    mock_cm.list_remotes.return_value = []

    mocker.patch('app.views.browser_interface.RClone', return_value=mock_rclone)
    mocker.patch('app.views.browser_interface.ConfigManager', return_value=mock_cm)

    return mock_rclone, mock_cm


def _make_settings_mocks(mocker):
    from app.common.config import CacheDirMode
    from qfluentwidgets import qconfig

    mock_rclone = MagicMock()
    mock_rclone.version.return_value = "rclone v1.68.0"

    mock_cfg = MagicMock()
    mock_cfg.rclonePath = MagicMock()
    mock_cfg.rclonePath.value = '/usr/bin/rclone'

    mock_cache_mode = MagicMock()
    mock_cache_mode.options = [CacheDirMode.DEFAULT, CacheDirMode.SYSTEM_TEMP, CacheDirMode.CUSTOM]
    mock_cache_mode.value = CacheDirMode.DEFAULT
    mock_cache_mode.defaultValue = CacheDirMode.DEFAULT
    mock_cfg.cacheDirMode = mock_cache_mode

    mock_cfg.cacheDirCustomPath = MagicMock()
    mock_cfg.cacheDirCustomPath.value = ''
    mock_cfg.themeMode = MagicMock()
    mock_cfg.autoStart = MagicMock()
    mock_cfg.autoStart.value = False
    mock_cfg.minimizeToTray = MagicMock()
    mock_cfg.closeToTray = MagicMock()
    mock_cfg.autoMount = MagicMock()

    original_qconfig_get = qconfig.get

    def patched_qconfig_get(item):
        if item is mock_cache_mode:
            return CacheDirMode.DEFAULT
        return original_qconfig_get(item)

    mocker.patch('app.views.settings_interface.RClone', return_value=mock_rclone)
    mocker.patch('app.views.settings_interface.is_auto_start_enabled', return_value=False)
    mocker.patch('app.views.settings_interface.set_auto_start', return_value=True)
    mocker.patch('app.views.settings_interface.cfg', mock_cfg)
    mocker.patch.object(qconfig, 'get', side_effect=patched_qconfig_get)

    return mock_rclone, mock_cfg


class TestGetSystemTheme:

    def test_non_windows_returns_light(self, mocker):
        mocker.patch.object(sys, 'platform', 'linux')
        from app.views.settings_interface import get_system_theme
        from qfluentwidgets import Theme
        assert get_system_theme() == Theme.LIGHT

    def test_darwin_returns_light(self, mocker):
        mocker.patch.object(sys, 'platform', 'darwin')
        from app.views.settings_interface import get_system_theme
        from qfluentwidgets import Theme
        assert get_system_theme() == Theme.LIGHT

    def test_windows_light_theme(self, mocker):
        mocker.patch.object(sys, 'platform', 'win32')
        mock_winreg = MagicMock()
        mock_winreg.ConnectRegistry.return_value = MagicMock()
        mock_winreg.OpenKey.return_value = MagicMock()
        mock_winreg.QueryValueEx.return_value = (1, None)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mocker.patch.dict('sys.modules', {'winreg': mock_winreg})
        from app.views.settings_interface import get_system_theme
        from qfluentwidgets import Theme
        result = get_system_theme()
        assert result == Theme.LIGHT

    def test_windows_dark_theme(self, mocker):
        mocker.patch.object(sys, 'platform', 'win32')
        mock_winreg = MagicMock()
        mock_winreg.ConnectRegistry.return_value = MagicMock()
        mock_winreg.OpenKey.return_value = MagicMock()
        mock_winreg.QueryValueEx.return_value = (0, None)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mocker.patch.dict('sys.modules', {'winreg': mock_winreg})
        from app.views.settings_interface import get_system_theme
        from qfluentwidgets import Theme
        result = get_system_theme()
        assert result == Theme.DARK

    def test_windows_registry_exception_returns_light(self, mocker):
        mocker.patch.object(sys, 'platform', 'win32')
        mock_winreg = MagicMock()
        mock_winreg.ConnectRegistry.side_effect = OSError("no registry")
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mocker.patch.dict('sys.modules', {'winreg': mock_winreg})
        from app.views.settings_interface import get_system_theme
        from qfluentwidgets import Theme
        assert get_system_theme() == Theme.LIGHT


class TestFileListWorker:

    def test_init_stores_attributes(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileListWorker
        mock_rc = MagicMock()
        worker = FileListWorker(mock_rc, "myremote:path")
        assert worker.rclone is mock_rc
        assert worker.remote_path == "myremote:path"
        assert worker._cancelled is False

    def test_cancel_sets_flag(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileListWorker
        mock_rc = MagicMock()
        worker = FileListWorker(mock_rc, "remote:path")
        worker.cancel()
        assert worker._cancelled is True

    def test_run_success(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileListWorker
        mock_rc = MagicMock()
        files = [{"Name": "a.txt", "IsDir": False}]
        mock_rc.lsjson.return_value = (True, files)

        worker = FileListWorker(mock_rc, "remote:path")
        results = []
        worker.finished.connect(lambda s, f, e: results.append((s, f, e)))
        worker.run()

        assert len(results) == 1
        assert results[0][0] is True
        assert results[0][1] == files
        assert results[0][2] == ""

    def test_run_failure(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileListWorker
        mock_rc = MagicMock()
        mock_rc.lsjson.return_value = (False, "connection error")

        worker = FileListWorker(mock_rc, "remote:path")
        results = []
        worker.finished.connect(lambda s, f, e: results.append((s, f, e)))
        worker.run()

        assert len(results) == 1
        assert results[0][0] is False
        assert results[0][1] == []
        assert "connection error" in results[0][2]

    def test_run_cancelled_before_lsjson(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileListWorker
        mock_rc = MagicMock()

        worker = FileListWorker(mock_rc, "remote:path")
        worker._cancelled = True
        results = []
        worker.finished.connect(lambda s, f, e: results.append((s, f, e)))
        worker.run()

        assert results[0][0] is False
        assert "取消" in results[0][2]
        mock_rc.lsjson.assert_not_called()

    def test_run_cancelled_after_lsjson(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileListWorker
        mock_rc = MagicMock()

        def lsjson_side_effect(path):
            worker._cancelled = True
            return (True, [{"Name": "file.txt"}])

        mock_rc.lsjson.side_effect = lsjson_side_effect

        worker = FileListWorker(mock_rc, "remote:path")
        results = []
        worker.finished.connect(lambda s, f, e: results.append((s, f, e)))
        worker.run()

        assert results[0][0] is False
        assert "取消" in results[0][2]


class TestFileOperationWorker:

    def test_init_stores_attributes(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()
        ops = [('copy', 'src', 'dst')]
        worker = FileOperationWorker(mock_rc, ops)
        assert worker.rclone is mock_rc
        assert worker.operations == ops
        assert worker._cancelled is False

    def test_cancel_sets_flag(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        worker = FileOperationWorker(MagicMock(), [])
        worker.cancel()
        assert worker._cancelled is True

    def test_run_copy_success(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()
        mock_rc.copy.return_value = FakeRCloneResult(success=True)

        worker = FileOperationWorker(mock_rc, [('copy', '/tmp/a.txt', 'remote:dir')])
        results = []
        worker.finished.connect(lambda s, m: results.append((s, m)))
        worker.run()

        mock_rc.copy.assert_called_once_with('/tmp/a.txt', 'remote:dir')
        assert results[0][0] is True

    def test_run_mkdir_success(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()
        mock_rc.mkdir.return_value = FakeRCloneResult(success=True)

        worker = FileOperationWorker(mock_rc, [('mkdir', 'remote:newdir')])
        results = []
        worker.finished.connect(lambda s, m: results.append((s, m)))
        worker.run()

        mock_rc.mkdir.assert_called_once_with('remote:newdir')
        assert results[0][0] is True

    def test_run_purge_success(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()
        mock_rc.purge.return_value = FakeRCloneResult(success=True)

        worker = FileOperationWorker(mock_rc, [('purge', 'remote:dir')])
        results = []
        worker.finished.connect(lambda s, m: results.append((s, m)))
        worker.run()

        mock_rc.purge.assert_called_once_with('remote:dir')
        assert results[0][0] is True

    def test_run_delete_file_success(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()
        mock_rc.delete_file.return_value = FakeRCloneResult(success=True)

        worker = FileOperationWorker(mock_rc, [('delete_file', 'remote:file.txt')])
        results = []
        worker.finished.connect(lambda s, m: results.append((s, m)))
        worker.run()

        mock_rc.delete_file.assert_called_once_with('remote:file.txt')
        assert results[0][0] is True

    def test_run_unknown_operation(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()

        worker = FileOperationWorker(mock_rc, [('unknown_op', 'arg1')])
        results = []
        worker.finished.connect(lambda s, m: results.append((s, m)))
        worker.run()

        assert results[0][0] is False
        assert "未知操作" in results[0][1]

    def test_run_operation_failure(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()
        mock_rc.copy.return_value = FakeRCloneResult(success=False, stderr="permission denied")

        worker = FileOperationWorker(mock_rc, [('copy', 'src', 'dst')])
        results = []
        worker.finished.connect(lambda s, m: results.append((s, m)))
        worker.run()

        assert results[0][0] is False
        assert "permission denied" in results[0][1]

    def test_run_cancelled_mid_operations(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()

        def copy_side_effect(*args):
            worker._cancelled = True
            return FakeRCloneResult(success=True)

        mock_rc.copy.side_effect = copy_side_effect

        ops = [('copy', 'a', 'b'), ('copy', 'c', 'd')]
        worker = FileOperationWorker(mock_rc, ops)
        results = []
        worker.finished.connect(lambda s, m: results.append((s, m)))
        worker.run()

        assert mock_rc.copy.call_count == 1
        assert results[0][0] is False
        assert "取消" in results[0][1]

    def test_run_emits_progress(self, mocker):
        _make_browser_mocks(mocker)
        from app.views.browser_interface import FileOperationWorker
        mock_rc = MagicMock()
        mock_rc.copy.return_value = FakeRCloneResult(success=True)
        mock_rc.mkdir.return_value = FakeRCloneResult(success=True)

        ops = [('copy', 'a', 'b'), ('mkdir', 'remote:dir')]
        worker = FileOperationWorker(mock_rc, ops)
        progress_msgs = []
        worker.progress.connect(lambda m: progress_msgs.append(m))
        results = []
        worker.finished.connect(lambda s, m: results.append((s, m)))
        worker.run()

        assert len(progress_msgs) == 2
        assert "copy" in progress_msgs[0]
        assert "mkdir" in progress_msgs[1]
        assert results[0][0] is True


class TestBrowserInterface:

    @pytest.fixture
    def browser(self, mocker):
        mock_rclone, mock_cm = _make_browser_mocks(mocker)
        mocker.patch('app.views.browser_interface.FileListWorker')
        from app.views.browser_interface import BrowserInterface
        widget = BrowserInterface()
        widget._mock_rclone = mock_rclone
        widget._mock_cm = mock_cm
        yield widget

    def test_build_remote_path_simple(self, browser):
        result = browser._build_remote_path("myremote", "docs/photos")
        assert result == "myremote:docs/photos"

    def test_build_remote_path_empty_path(self, browser):
        result = browser._build_remote_path("myremote", "")
        assert result == "myremote:"

    def test_build_remote_path_root_slash(self, browser):
        result = browser._build_remote_path("myremote", "/")
        assert result == "myremote:"

    def test_build_remote_path_traversal_dots(self, browser):
        result = browser._build_remote_path("myremote", "a/../b")
        assert ".." not in result
        assert result == "myremote:a/b"

    def test_build_remote_path_traversal_only_dots(self, browser):
        result = browser._build_remote_path("myremote", "../../..")
        assert result == "myremote:"

    def test_build_remote_path_single_dot(self, browser):
        result = browser._build_remote_path("myremote", "./a/./b")
        assert result == "myremote:a/b"

    def test_build_remote_path_backslash_normalized(self, browser):
        result = browser._build_remote_path("myremote", "a\\b\\c")
        assert result == "myremote:a/b/c"

    def test_build_remote_path_invalid_remote_name_dots(self, browser):
        with pytest.raises(ValueError):
            browser._build_remote_path("my..remote", "path")

    def test_build_remote_path_invalid_remote_name_slash(self, browser):
        with pytest.raises(ValueError):
            browser._build_remote_path("my/remote", "path")

    def test_build_remote_path_invalid_remote_name_backslash(self, browser):
        with pytest.raises(ValueError):
            browser._build_remote_path("my\\remote", "path")

    def test_build_remote_path_empty_remote_name(self, browser):
        with pytest.raises(ValueError):
            browser._build_remote_path("", "path")

    def test_format_size_bytes(self, browser):
        assert browser.formatSize(0) == "0.0 B"
        assert browser.formatSize(512) == "512.0 B"

    def test_format_size_kb(self, browser):
        assert browser.formatSize(1024) == "1.0 KB"
        assert browser.formatSize(1536) == "1.5 KB"

    def test_format_size_mb(self, browser):
        result = browser.formatSize(1024 * 1024)
        assert result == "1.0 MB"

    def test_format_size_gb(self, browser):
        result = browser.formatSize(1024 ** 3)
        assert result == "1.0 GB"

    def test_format_size_tb(self, browser):
        result = browser.formatSize(1024 ** 4)
        assert result == "1.0 TB"

    def test_format_size_pb(self, browser):
        result = browser.formatSize(1024 ** 5)
        assert result == "1.0 PB"

    def test_on_refresh_finished_success_with_files(self, browser, mocker):
        mock_infobar = mocker.patch('app.views.browser_interface.InfoBar')
        files = [
            {"Name": "photo.jpg", "IsDir": False, "Size": 2048, "ModTime": "2024-01-15T10:30:00Z"},
            {"Name": "docs", "IsDir": True, "Size": 0, "ModTime": "2024-01-10T08:00:00Z"},
        ]
        browser._on_refresh_finished(True, files, "")

        assert browser.fileTree.topLevelItemCount() == 2
        item0 = browser.fileTree.topLevelItem(0)
        assert item0.text(0) == "photo.jpg"
        assert "KB" in item0.text(1)
        assert "2024-01-15 10:30:00" in item0.text(2)
        item1 = browser.fileTree.topLevelItem(1)
        assert item1.text(0) == "docs"
        assert item1.text(1) == "-"
        mock_infobar.error.assert_not_called()

    def test_on_refresh_finished_success_empty(self, browser, mocker):
        mocker.patch('app.views.browser_interface.InfoBar')
        browser._on_refresh_finished(True, [], "")
        assert browser.fileTree.topLevelItemCount() == 0

    def test_on_refresh_finished_failure(self, browser, mocker):
        mock_infobar = mocker.patch('app.views.browser_interface.InfoBar')
        browser._on_refresh_finished(False, [], "Network error")
        mock_infobar.error.assert_called_once()
        assert browser.fileTree.topLevelItemCount() == 0

    def test_set_loading_state_true(self, browser):
        browser._set_loading_state(True)
        assert not browser.fileTree.isEnabled()
        assert not browser.refreshBtn.isEnabled()
        assert not browser.remoteCombo.isEnabled()

    def test_set_loading_state_false(self, browser):
        browser._set_loading_state(True)
        browser._set_loading_state(False)
        assert browser.fileTree.isEnabled()
        assert browser.refreshBtn.isEnabled()
        assert browser.remoteCombo.isEnabled()

    def test_go_up_from_subdir(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = "myremote"
        browser.currentPath = "a/b/c"
        browser.goUp()
        assert browser.currentPath == "a/b"
        assert browser.pathEdit.text() == "/a/b"

    def test_go_up_from_root_child(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = "myremote"
        browser.currentPath = "docs"
        browser.goUp()
        assert browser.currentPath == ""
        assert browser.pathEdit.text() == "/"

    def test_go_up_from_root(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = "myremote"
        browser.currentPath = ""
        browser.goUp()
        assert browser.currentPath == ""

    def test_go_home(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = "myremote"
        browser.currentPath = "a/b/c"
        browser.goHome()
        assert browser.currentPath == ""
        assert browser.pathEdit.text() == "/"

    def test_navigate_to_path(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = "myremote"
        browser.pathEdit.setText("/some/deep/path/")
        browser.navigateToPath()
        assert browser.currentPath == "some/deep/path"

    def test_load_remotes_with_remotes(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        from app.models.remote import Remote
        r1 = Remote(name="mywebdav", type="webdav")
        r2 = Remote(name="s3bucket", type="s3")
        browser._mock_cm.list_remotes.return_value = [r1, r2]

        browser.loadRemotes()

        assert browser.remoteCombo.count() == 2
        assert browser.remoteCombo.itemText(0) == "mywebdav"
        assert browser.remoteCombo.itemText(1) == "s3bucket"
        assert browser.currentRemote == "mywebdav"

    def test_load_remotes_empty(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser._mock_cm.list_remotes.return_value = []
        browser.loadRemotes()
        assert browser.remoteCombo.count() == 0

    def test_on_remote_changed(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        from app.models.remote import Remote
        browser._mock_cm.list_remotes.return_value = [
            Remote(name="r1", type="s3"),
            Remote(name="r2", type="sftp"),
        ]
        browser.loadRemotes()
        browser.currentPath = "some/path"

        browser.remoteCombo.setCurrentIndex(1)
        assert browser.currentPath == ""
        assert browser.pathEdit.text() == "/"

    def test_on_item_double_clicked_directory(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = "myremote"
        browser.currentPath = ""

        item = QTreeWidgetItem()
        item.setText(0, "subdir")
        item.setData(0, Qt.UserRole, {"Name": "subdir", "IsDir": True})

        browser.onItemDoubleClicked(item, 0)
        assert browser.currentPath == "subdir"
        assert browser.pathEdit.text() == "/subdir"

    def test_on_item_double_clicked_directory_nested(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = "myremote"
        browser.currentPath = "parent"

        item = QTreeWidgetItem()
        item.setData(0, Qt.UserRole, {"Name": "child", "IsDir": True})

        browser.onItemDoubleClicked(item, 0)
        assert browser.currentPath == "parent/child"

    def test_on_item_double_clicked_file(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = "myremote"
        browser.currentPath = ""

        item = QTreeWidgetItem()
        item.setData(0, Qt.UserRole, {"Name": "file.txt", "IsDir": False})

        browser.onItemDoubleClicked(item, 0)
        assert browser.currentPath == ""

    def test_upload_file_with_selection(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_dialog = mocker.patch(
            'app.views.browser_interface.QFileDialog.getOpenFileNames',
            return_value=(['/tmp/a.txt', '/tmp/b.txt'], '')
        )
        mock_exec = mocker.patch.object(browser, '_execute_operations')
        browser.currentRemote = "myremote"
        browser.currentPath = "uploads"

        browser.uploadFile()

        mock_exec.assert_called_once()
        ops = mock_exec.call_args[0][0]
        assert len(ops) == 2
        assert ops[0][0] == 'copy'
        assert ops[0][1] == '/tmp/a.txt'
        assert ops[0][2] == 'myremote:uploads'

    def test_upload_file_cancelled(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mocker.patch(
            'app.views.browser_interface.QFileDialog.getOpenFileNames',
            return_value=([], '')
        )
        mock_exec = mocker.patch.object(browser, '_execute_operations')
        browser.uploadFile()
        mock_exec.assert_not_called()

    def test_download_file_with_selection(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mocker.patch(
            'app.views.browser_interface.QFileDialog.getExistingDirectory',
            return_value='/home/user/downloads'
        )
        mock_exec = mocker.patch.object(browser, '_execute_operations')
        browser.currentRemote = "myremote"
        browser.currentPath = "docs"

        item = QTreeWidgetItem()
        item.setData(0, Qt.UserRole, {"Name": "report.pdf", "IsDir": False})
        browser.fileTree.addTopLevelItem(item)
        item.setSelected(True)

        browser.downloadFile()

        mock_exec.assert_called_once()
        ops = mock_exec.call_args[0][0]
        assert len(ops) == 1
        assert ops[0] == ('copy', 'myremote:docs/report.pdf', '/home/user/downloads')

    def test_download_file_no_selection(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_infobar = mocker.patch('app.views.browser_interface.InfoBar')
        browser.downloadFile()
        mock_infobar.warning.assert_called_once()

    def test_download_file_dialog_cancelled(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mocker.patch(
            'app.views.browser_interface.QFileDialog.getExistingDirectory',
            return_value=''
        )
        mock_exec = mocker.patch.object(browser, '_execute_operations')

        item = QTreeWidgetItem()
        item.setData(0, Qt.UserRole, {"Name": "file.txt", "IsDir": False})
        browser.fileTree.addTopLevelItem(item)
        item.setSelected(True)

        browser.downloadFile()
        mock_exec.assert_not_called()

    def test_create_folder_success(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_exec = mocker.patch.object(browser, '_execute_operations')
        browser.currentRemote = "myremote"
        browser.currentPath = "parent"

        mock_msgbox_cls = mocker.patch('app.views.browser_interface.MessageBox')
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_msgbox_cls.return_value = mock_dialog

        mock_line_edit_cls = mocker.patch('app.views.browser_interface.LineEdit')
        mock_name_edit = MagicMock()
        mock_name_edit.text.return_value = "newfolder"
        mock_line_edit_cls.return_value = mock_name_edit

        browser.createFolder()

        mock_exec.assert_called_once()
        ops = mock_exec.call_args[0][0]
        assert ops[0][0] == 'mkdir'
        assert ops[0][1] == 'myremote:parent/newfolder'

    def test_create_folder_invalid_name(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_infobar = mocker.patch('app.views.browser_interface.InfoBar')
        mock_exec = mocker.patch.object(browser, '_execute_operations')
        browser.currentRemote = "myremote"
        browser.currentPath = ""

        mock_msgbox_cls = mocker.patch('app.views.browser_interface.MessageBox')
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_msgbox_cls.return_value = mock_dialog

        mock_line_edit_cls = mocker.patch('app.views.browser_interface.LineEdit')
        mock_name_edit = MagicMock()
        mock_name_edit.text.return_value = "../escape"
        mock_line_edit_cls.return_value = mock_name_edit

        browser.createFolder()

        mock_exec.assert_not_called()
        mock_infobar.error.assert_called_once()

    def test_create_folder_cancelled(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_exec = mocker.patch.object(browser, '_execute_operations')

        mock_msgbox_cls = mocker.patch('app.views.browser_interface.MessageBox')
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = False
        mock_msgbox_cls.return_value = mock_dialog

        mocker.patch('app.views.browser_interface.LineEdit')

        browser.createFolder()
        mock_exec.assert_not_called()

    def test_delete_selected_files_and_dirs(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_exec = mocker.patch.object(browser, '_execute_operations')
        browser.currentRemote = "myremote"
        browser.currentPath = "data"

        mock_msgbox_cls = mocker.patch('app.views.browser_interface.MessageBox')
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_msgbox_cls.return_value = mock_dialog

        file_item = QTreeWidgetItem()
        file_item.setData(0, Qt.UserRole, {"Name": "file.txt", "IsDir": False})
        browser.fileTree.addTopLevelItem(file_item)
        file_item.setSelected(True)

        dir_item = QTreeWidgetItem()
        dir_item.setData(0, Qt.UserRole, {"Name": "subdir", "IsDir": True})
        browser.fileTree.addTopLevelItem(dir_item)
        dir_item.setSelected(True)

        browser.deleteSelected()

        mock_exec.assert_called_once()
        ops = mock_exec.call_args[0][0]
        assert len(ops) == 2
        op_types = {op[0] for op in ops}
        assert 'delete_file' in op_types
        assert 'purge' in op_types

    def test_delete_selected_no_selection(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_infobar = mocker.patch('app.views.browser_interface.InfoBar')
        browser.deleteSelected()
        mock_infobar.warning.assert_called_once()

    def test_delete_selected_cancelled(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_exec = mocker.patch.object(browser, '_execute_operations')

        mock_msgbox_cls = mocker.patch('app.views.browser_interface.MessageBox')
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = False
        mock_msgbox_cls.return_value = mock_dialog

        item = QTreeWidgetItem()
        item.setData(0, Qt.UserRole, {"Name": "file.txt", "IsDir": False})
        browser.fileTree.addTopLevelItem(item)
        item.setSelected(True)

        browser.deleteSelected()
        mock_exec.assert_not_called()

    def test_on_operation_finished_success(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_infobar = mocker.patch('app.views.browser_interface.InfoBar')
        mock_timer = mocker.patch('app.views.browser_interface.QTimer')

        browser._on_operation_finished(True, "done", "Upload complete", "Upload failed")

        mock_infobar.success.assert_called_once()
        assert "Upload complete" in str(mock_infobar.success.call_args)
        # refresh 通过 QTimer.singleShot(0, ...) 延迟调用，避免在 worker finished 信号链中崩溃
        mock_timer.singleShot.assert_called_once_with(0, browser.refresh)

    def test_on_operation_finished_failure(self, browser, mocker):
        mocker.patch('app.views.browser_interface.FileListWorker')
        mock_infobar = mocker.patch('app.views.browser_interface.InfoBar')
        mock_refresh = mocker.patch.object(browser, 'refresh')

        browser._on_operation_finished(False, "timeout", "Upload complete", "Upload failed")

        mock_infobar.error.assert_called_once()
        assert "Upload failed" in str(mock_infobar.error.call_args)
        mock_refresh.assert_not_called()

    def test_on_operation_progress(self, browser, mocker):
        mock_infobar = mocker.patch('app.views.browser_interface.InfoBar')
        browser._on_operation_progress("Copying file.txt...")
        mock_infobar.info.assert_called_once()

    def test_refresh_no_remote(self, browser, mocker):
        mock_worker_cls = mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = ""
        browser.refresh()
        mock_worker_cls.assert_not_called()

    def test_refresh_creates_worker(self, browser, mocker):
        mock_worker_cls = mocker.patch('app.views.browser_interface.FileListWorker')
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = False
        mock_worker_cls.return_value = mock_worker

        browser.currentRemote = "myremote"
        browser.currentPath = "docs"
        browser._current_worker = None

        browser.refresh()

        mock_worker_cls.assert_called_once()
        call_args = mock_worker_cls.call_args
        assert call_args[0][1] == "myremote:docs"
        mock_worker.start.assert_called_once()


class TestSettingsInterface:

    @pytest.fixture
    def settings(self, mocker):
        mock_rclone, mock_cfg = _make_settings_mocks(mocker)
        from app.views.settings_interface import SettingsInterface
        widget = SettingsInterface()
        widget._mock_rclone = mock_rclone
        widget._mock_cfg = mock_cfg
        yield widget

    def test_select_rclone_path_chosen(self, settings, mocker):
        mocker.patch(
            'app.views.settings_interface.QFileDialog.getOpenFileName',
            return_value=('/opt/rclone/rclone', '')
        )
        settings._mock_rclone.version.return_value = "rclone v1.70.0"

        settings.selectRclonePath()

        assert settings._mock_cfg.rclonePath.value == '/opt/rclone/rclone'
        assert settings._mock_rclone.rclone_path == '/opt/rclone/rclone'
        assert settings.rclonePathCard.contentLabel.text() == '/opt/rclone/rclone'

    def test_select_rclone_path_cancelled(self, settings, mocker):
        mocker.patch(
            'app.views.settings_interface.QFileDialog.getOpenFileName',
            return_value=('', '')
        )
        original_content = settings.rclonePathCard.contentLabel.text()
        settings.selectRclonePath()
        assert settings.rclonePathCard.contentLabel.text() == original_content

    def test_select_cache_dir_chosen(self, settings, mocker):
        mocker.patch(
            'app.views.settings_interface.QFileDialog.getExistingDirectory',
            return_value='/tmp/rclone_cache'
        )

        settings.selectCacheDir()

        assert settings._mock_cfg.cacheDirCustomPath.value == '/tmp/rclone_cache'
        assert settings.cacheDirCustomCard.contentLabel.text() == '/tmp/rclone_cache'

    def test_select_cache_dir_cancelled(self, settings, mocker):
        mocker.patch(
            'app.views.settings_interface.QFileDialog.getExistingDirectory',
            return_value=''
        )
        original_content = settings.cacheDirCustomCard.contentLabel.text()
        settings.selectCacheDir()
        assert settings.cacheDirCustomCard.contentLabel.text() == original_content

    def test_on_theme_changed_light(self, settings, mocker):
        from qfluentwidgets import Theme
        mock_set_theme = mocker.patch('app.views.settings_interface.setTheme')
        mock_signal = mocker.patch('app.views.settings_interface.signalBus')

        mock_config_item = MagicMock()
        mock_config_item.value = Theme.LIGHT
        settings.onThemeChanged(mock_config_item)

        mock_set_theme.assert_called_once_with(Theme.LIGHT)
        mock_signal.themeChanged.emit.assert_called_once()

    def test_on_theme_changed_dark(self, settings, mocker):
        from qfluentwidgets import Theme
        mock_set_theme = mocker.patch('app.views.settings_interface.setTheme')
        mock_signal = mocker.patch('app.views.settings_interface.signalBus')

        mock_config_item = MagicMock()
        mock_config_item.value = Theme.DARK
        settings.onThemeChanged(mock_config_item)

        mock_set_theme.assert_called_once_with(Theme.DARK)
        mock_signal.themeChanged.emit.assert_called_once()

    def test_on_theme_changed_auto(self, settings, mocker):
        from qfluentwidgets import Theme
        mock_set_theme = mocker.patch('app.views.settings_interface.setTheme')
        mock_signal = mocker.patch('app.views.settings_interface.signalBus')
        mocker.patch(
            'app.views.settings_interface.get_system_theme',
            return_value=Theme.LIGHT
        )

        mock_config_item = MagicMock()
        mock_config_item.value = Theme.AUTO
        settings.onThemeChanged(mock_config_item)

        mock_set_theme.assert_called_once_with(Theme.LIGHT, save=False)
        mock_signal.themeChanged.emit.assert_called_once()

    def test_sync_auto_start_registry_differs_from_config(self, settings, mocker):
        mock_is_auto = mocker.patch(
            'app.views.settings_interface.is_auto_start_enabled',
            return_value=True
        )
        settings._mock_cfg.autoStart.value = False

        settings.syncAutoStartState()

        assert settings._mock_cfg.autoStart.value is True

    def test_sync_auto_start_already_in_sync(self, settings, mocker):
        mocker.patch(
            'app.views.settings_interface.is_auto_start_enabled',
            return_value=False
        )
        settings._mock_cfg.autoStart.value = False

        settings.syncAutoStartState()
        assert settings._mock_cfg.autoStart.value is False

    def test_sync_auto_start_exception(self, settings, mocker):
        mocker.patch(
            'app.views.settings_interface.is_auto_start_enabled',
            side_effect=OSError("registry error")
        )
        settings.syncAutoStartState()

    def test_on_auto_start_changed_enable_success(self, settings, mocker):
        mocker.patch('app.views.settings_interface.set_auto_start', return_value=True)
        mock_infobar = mocker.patch('app.views.settings_interface.InfoBar')

        settings.onAutoStartChanged(True)

        mock_infobar.success.assert_called_once()

    def test_on_auto_start_changed_disable_success(self, settings, mocker):
        mocker.patch('app.views.settings_interface.set_auto_start', return_value=True)
        mock_infobar = mocker.patch('app.views.settings_interface.InfoBar')

        settings.onAutoStartChanged(False)

        mock_infobar.success.assert_called_once()

    def test_on_auto_start_changed_failure(self, settings, mocker):
        mocker.patch('app.views.settings_interface.set_auto_start', return_value=False)
        mock_infobar = mocker.patch('app.views.settings_interface.InfoBar')

        settings.onAutoStartChanged(True)

        mock_infobar.error.assert_called_once()

    def test_show_rclone_version(self, settings, mocker):
        mock_msgbox = mocker.patch('PySide6.QtWidgets.QMessageBox')
        settings._mock_rclone.version.return_value = "rclone v1.68.0"

        settings.showRcloneVersion()

        mock_msgbox.information.assert_called_once()
        call_args_str = str(mock_msgbox.information.call_args)
        assert "v1.68.0" in call_args_str

    def test_open_project_url(self, settings, mocker):
        mock_webbrowser = MagicMock()
        mocker.patch.dict('sys.modules', {'webbrowser': mock_webbrowser})
        mock_infobar = mocker.patch('app.views.settings_interface.InfoBar')

        settings.openProjectUrl()

        mock_webbrowser.open.assert_called_once_with('https://github.com/GamblerIX/RCloneGUI')
        mock_infobar.success.assert_called_once()


class TestBrowserInterfaceSignals:
    """测试 BrowserInterface 的信号处理方法。"""

    @pytest.fixture
    def browser(self, mocker):
        mock_rclone, mock_cm = _make_browser_mocks(mocker)
        mocker.patch('app.views.browser_interface.FileListWorker')
        from app.views.browser_interface import BrowserInterface
        widget = BrowserInterface()
        widget._mock_rclone = mock_rclone
        widget._mock_cm = mock_cm
        yield widget

    def test_onRemoteChanged_signal_refreshes_remotes(self, browser, mocker):
        """onRemoteChanged_signal 触发时刷新远程存储列表（lines 120-121）。"""
        mocker.patch.object(browser, 'loadRemotes')
        browser.onRemoteChanged_signal('test-remote')
        browser.loadRemotes.assert_called_once()

    def test_onRemoteRemoved_resets_when_current(self, browser, mocker):
        """onRemoteRemoved 当前浏览的远程存储被删除时重置状态（lines 124-131）。"""
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = 'deleted-remote'
        browser.currentPath = 'some/path'

        mocker.patch.object(browser, 'loadRemotes')
        browser.onRemoteRemoved('deleted-remote')

        assert browser.currentRemote == ''
        assert browser.currentPath == ''
        assert browser.pathEdit.text() == '/'
        browser.loadRemotes.assert_called_once()

    def test_onRemoteRemoved_no_reset_when_different(self, browser, mocker):
        """onRemoteRemoved 删除的不是当前浏览的远程存储时不重置（lines 124-131）。"""
        mocker.patch('app.views.browser_interface.FileListWorker')
        browser.currentRemote = 'other-remote'
        browser.currentPath = 'some/path'

        mocker.patch.object(browser, 'loadRemotes')
        browser.onRemoteRemoved('deleted-remote')

        assert browser.currentRemote == 'other-remote'
        assert browser.currentPath == 'some/path'
        browser.loadRemotes.assert_called_once()


class TestSettingsInterfaceCacheDirPaths:
    """测试 SettingsInterface 中缓存目录相关的未覆盖路径。"""

    @pytest.fixture
    def settings(self, mocker):
        mock_rclone, mock_cfg = _make_settings_mocks(mocker)
        from app.views.settings_interface import SettingsInterface
        widget = SettingsInterface()
        widget._mock_cfg = mock_cfg
        yield widget

    def test_onCacheDirModeChanged_to_custom(self, settings, mocker):
        """onCacheDirModeChanged 切换到自定义模式（lines 197-201）。"""
        from app.common.config import CacheDirMode
        settings._mock_cfg.cacheDirMode.value = CacheDirMode.CUSTOM
        settings.onCacheDirModeChanged(2)  # index 2 = CUSTOM
        # Use isHidden() because isVisible() requires parent to be shown
        assert not settings.cacheDirCustomCard.isHidden()

    def test_onCacheDirModeChanged_to_default(self, settings, mocker):
        """onCacheDirModeChanged 切换到默认模式。"""
        settings.onCacheDirModeChanged(0)  # index 0 = DEFAULT
        assert settings.cacheDirCustomCard.isHidden()

    def test_onCacheDirModeChanged_to_system_temp(self, settings, mocker):
        """onCacheDirModeChanged 切换到系统临时目录模式。"""
        settings.onCacheDirModeChanged(1)  # index 1 = SYSTEM_TEMP
        assert settings.cacheDirCustomCard.isHidden()

    def test_get_cache_dir_description_system_temp(self, settings, mocker):
        """_get_cache_dir_description 系统临时目录模式（lines 207-209）。"""
        import tempfile
        from app.common.config import CacheDirMode
        settings._mock_cfg.cacheDirMode.value = CacheDirMode.SYSTEM_TEMP
        result = settings._get_cache_dir_description()
        assert result == tempfile.gettempdir()

    def test_get_cache_dir_description_custom_with_path(self, settings, mocker):
        """_get_cache_dir_description 自定义模式有路径（lines 210-211）。"""
        from app.common.config import CacheDirMode
        settings._mock_cfg.cacheDirMode.value = CacheDirMode.CUSTOM
        settings._mock_cfg.cacheDirCustomPath.value = 'D:\\my_cache'
        result = settings._get_cache_dir_description()
        assert result == 'D:\\my_cache'

    def test_get_cache_dir_description_custom_no_path(self, settings, mocker):
        """_get_cache_dir_description 自定义模式无路径（line 211）。"""
        from app.common.config import CacheDirMode
        settings._mock_cfg.cacheDirMode.value = CacheDirMode.CUSTOM
        settings._mock_cfg.cacheDirCustomPath.value = ''
        result = settings._get_cache_dir_description()
        assert result == '未设置，请选择目录'
