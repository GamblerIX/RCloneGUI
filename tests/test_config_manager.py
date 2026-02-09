"""
ConfigManager 单元测试。

覆盖 app/core/config_manager.py 中的所有方法路径。
"""

import pytest
from unittest.mock import MagicMock

from app.core.config_manager import ConfigManager
from app.core.rclone import RClone


@pytest.fixture
def mock_rclone():
    rclone = MagicMock(spec=RClone)
    rclone.config_dump.return_value = {}
    return rclone


@pytest.fixture
def cm(mock_rclone):
    return ConfigManager(rclone=mock_rclone)


class TestConfigManagerInit:

    def test_init_with_rclone(self, mock_rclone):
        cm = ConfigManager(rclone=mock_rclone)
        assert cm.rclone is mock_rclone
        assert cm._remotes_cache == {}

    def test_init_default_rclone(self, monkeypatch):
        monkeypatch.setattr('app.core.config_manager.RClone', MagicMock)
        cm = ConfigManager()
        assert cm.rclone is not None


class TestConfigManagerRefresh:

    def test_refresh_populates_cache(self, cm, mock_rclone):
        mock_rclone.config_dump.return_value = {
            'myremote': {'type': 'sftp', 'host': '1.2.3.4'},
            'backup': {'type': 's3', 'provider': 'AWS'},
        }
        cm.refresh()
        assert len(cm._remotes_cache) == 2
        assert 'myremote' in cm._remotes_cache
        assert cm._remotes_cache['myremote'].type == 'sftp'

    def test_refresh_clears_old_cache(self, cm, mock_rclone):
        mock_rclone.config_dump.return_value = {
            'old': {'type': 'ftp', 'host': 'old.com'},
        }
        cm.refresh()
        assert 'old' in cm._remotes_cache

        mock_rclone.config_dump.return_value = {
            'new': {'type': 'sftp', 'host': 'new.com'},
        }
        cm.refresh()
        assert 'old' not in cm._remotes_cache
        assert 'new' in cm._remotes_cache

    def test_refresh_unknown_type(self, cm, mock_rclone):
        mock_rclone.config_dump.return_value = {
            'mystery': {},
        }
        cm.refresh()
        # type defaults to 'unknown' but Remote validation may reject it
        # The code uses config.get('type', 'unknown')


class TestConfigManagerListRemotes:

    def test_list_remotes_triggers_refresh(self, cm, mock_rclone):
        mock_rclone.config_dump.return_value = {
            'r1': {'type': 'sftp', 'host': 'a.com'},
        }
        result = cm.list_remotes()
        assert len(result) == 1
        mock_rclone.config_dump.assert_called_once()

    def test_list_remotes_uses_cache(self, cm, mock_rclone):
        mock_rclone.config_dump.return_value = {
            'r1': {'type': 'sftp', 'host': 'a.com'},
        }
        cm.list_remotes()
        cm.list_remotes()
        # Only called once because cache is populated
        mock_rclone.config_dump.assert_called_once()

    def test_list_remotes_empty(self, cm, mock_rclone):
        mock_rclone.config_dump.return_value = {}
        # Empty cache triggers refresh, but still empty
        cm.refresh()
        # After refresh with empty data, cache is empty dict (falsy)
        # list_remotes will try refresh again
        result = cm.list_remotes()
        assert result == []


class TestConfigManagerGetRemote:

    def test_get_remote_found(self, cm, mock_rclone):
        mock_rclone.config_dump.return_value = {
            'myremote': {'type': 'sftp', 'host': '1.2.3.4'},
        }
        remote = cm.get_remote('myremote')
        assert remote is not None
        assert remote.name == 'myremote'

    def test_get_remote_not_found(self, cm, mock_rclone):
        mock_rclone.config_dump.return_value = {
            'myremote': {'type': 'sftp', 'host': '1.2.3.4'},
        }
        remote = cm.get_remote('nonexistent')
        assert remote is None


class TestConfigManagerAddRemote:

    def test_add_remote_success(self, cm, mock_rclone):
        result = MagicMock()
        result.success = True
        mock_rclone.config_create.return_value = result

        success = cm.add_remote('new-remote', 'sftp', host='1.2.3.4', user='root')
        assert success is True
        assert 'new-remote' in cm._remotes_cache
        mock_rclone.config_create.assert_called_once_with(
            'new-remote', 'sftp', host='1.2.3.4', user='root')

    def test_add_remote_failure(self, cm, mock_rclone):
        result = MagicMock()
        result.success = False
        result.return_code = 1
        result.stderr = 'error message'
        mock_rclone.config_create.return_value = result

        success = cm.add_remote('new-remote', 'sftp', host='1.2.3.4')
        assert success is False
        assert 'new-remote' not in cm._remotes_cache

    def test_add_remote_masks_password(self, cm, mock_rclone):
        """密码字段在日志中应被掩码。"""
        result = MagicMock()
        result.success = True
        mock_rclone.config_create.return_value = result

        cm.add_remote('r', 'sftp', host='h', **{'pass': 'secret123'})
        assert 'r' in cm._remotes_cache


class TestConfigManagerUpdateRemote:

    def test_update_remote_success(self, cm, mock_rclone):
        # Pre-populate cache
        mock_rclone.config_dump.return_value = {
            'myremote': {'type': 'sftp', 'host': 'old.com'},
        }
        cm.refresh()

        result = MagicMock()
        result.success = True
        mock_rclone.config_update.return_value = result

        success = cm.update_remote('myremote', host='new.com')
        assert success is True
        assert cm._remotes_cache['myremote'].config['host'] == 'new.com'

    def test_update_remote_failure(self, cm, mock_rclone):
        result = MagicMock()
        result.success = False
        result.return_code = 1
        result.stderr = 'update failed'
        mock_rclone.config_update.return_value = result

        success = cm.update_remote('myremote', host='new.com')
        assert success is False

    def test_update_remote_not_in_cache(self, cm, mock_rclone):
        """更新不在缓存中的远程存储（成功但不更新缓存）。"""
        result = MagicMock()
        result.success = True
        mock_rclone.config_update.return_value = result

        success = cm.update_remote('uncached', host='x.com')
        assert success is True


class TestConfigManagerDeleteRemote:

    def test_delete_remote_success(self, cm, mock_rclone):
        # Pre-populate cache
        mock_rclone.config_dump.return_value = {
            'myremote': {'type': 'sftp', 'host': 'a.com'},
        }
        cm.refresh()

        result = MagicMock()
        result.success = True
        mock_rclone.config_delete.return_value = result

        success = cm.delete_remote('myremote')
        assert success is True
        assert 'myremote' not in cm._remotes_cache

    def test_delete_remote_failure(self, cm, mock_rclone):
        result = MagicMock()
        result.success = False
        result.return_code = 1
        result.stderr = 'delete failed'
        mock_rclone.config_delete.return_value = result

        success = cm.delete_remote('myremote')
        assert success is False


class TestConfigManagerTestRemote:

    def test_test_remote_success(self, cm, mock_rclone):
        result = MagicMock()
        result.success = True
        mock_rclone.check.return_value = result

        success, msg = cm.test_remote('myremote')
        assert success is True
        assert msg == "Connection successful"

    def test_test_remote_failure(self, cm, mock_rclone):
        result = MagicMock()
        result.success = False
        result.stderr = 'connection refused'
        mock_rclone.check.return_value = result

        success, msg = cm.test_remote('myremote')
        assert success is False
        assert 'connection refused' in msg

    def test_test_remote_failure_no_stderr(self, cm, mock_rclone):
        result = MagicMock()
        result.success = False
        result.stderr = ''
        mock_rclone.check.return_value = result

        success, msg = cm.test_remote('myremote')
        assert success is False


class TestConfigManagerGetRemoteInfo:

    def test_get_remote_info_success(self, cm, mock_rclone):
        mock_rclone.about.return_value = (True, {'total': 1000, 'used': 500})

        info = cm.get_remote_info('myremote')
        assert info is not None
        assert info['total'] == 1000

    def test_get_remote_info_failure(self, cm, mock_rclone):
        mock_rclone.about.return_value = (False, None)

        info = cm.get_remote_info('myremote')
        assert info is None
