import pytest
import json
from unittest.mock import MagicMock, patch


class TestRCloneResult:

    def test_rclone_result_creation(self):
        from app.core.rclone import RCloneResult

        result = RCloneResult(
            success=True,
            stdout='output',
            stderr='',
            return_code=0
        )

        assert result.success is True
        assert result.stdout == 'output'
        assert result.stderr == ''
        assert result.return_code == 0

    def test_rclone_result_failure(self):
        from app.core.rclone import RCloneResult

        result = RCloneResult(
            success=False,
            stdout='',
            stderr='error message',
            return_code=1
        )

        assert result.success is False
        assert result.stderr == 'error message'
        assert result.return_code == 1


class TestRClone:

    @pytest.fixture
    def rclone(self, mocker):
        mocker.patch('app.core.rclone._resolve_path', side_effect=lambda x: x)
        mock_cfg = mocker.patch('app.core.rclone.cfg')
        mock_cfg.rcloneConfigPath.value = ''
        from app.core.rclone import RClone
        return RClone(rclone_path='rclone.exe', config_path=None)

    @pytest.fixture
    def rclone_with_config(self, mocker):
        mocker.patch('app.core.rclone._resolve_path', side_effect=lambda x: x)
        mocker.patch('app.core.rclone.cfg')
        from app.core.rclone import RClone
        return RClone(rclone_path='rclone.exe', config_path='/path/to/rclone.conf')

    def test_build_command_basic(self, rclone):
        cmd = rclone._build_command('listremotes')
        assert cmd == ['rclone.exe', 'listremotes']

    def test_build_command_with_config(self, rclone_with_config):
        cmd = rclone_with_config._build_command('listremotes')
        assert cmd == ['rclone.exe', '--config', '/path/to/rclone.conf', 'listremotes']

    def test_build_command_with_kwargs(self, rclone):
        cmd = rclone._build_command('copy', 'src', 'dst', dry_run=True, bwlimit='10M')
        assert 'rclone.exe' in cmd
        assert 'copy' in cmd
        assert 'src' in cmd
        assert 'dst' in cmd
        assert '--dry-run' in cmd
        assert '--bwlimit' in cmd
        assert '10M' in cmd

    def test_build_command_with_false_kwarg(self, rclone):
        cmd = rclone._build_command('sync', dry_run=False)
        assert '--dry-run' not in cmd

    def test_build_command_with_none_kwarg(self, rclone):
        cmd = rclone._build_command('sync', bwlimit=None)
        assert '--bwlimit' not in cmd

    @patch('subprocess.run')
    def test_run_success(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='success output',
            stderr=''
        )

        result = rclone._run('listremotes')

        assert result.success is True
        assert result.stdout == 'success output'
        assert result.return_code == 0

    @patch('subprocess.run')
    def test_run_failure(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='error occurred'
        )

        result = rclone._run('invalid')

        assert result.success is False
        assert result.stderr == 'error occurred'
        assert result.return_code == 1

    @patch('subprocess.run')
    def test_run_exception(self, mock_run, rclone):
        import subprocess
        mock_run.side_effect = subprocess.SubprocessError('Command failed')

        result = rclone._run('listremotes')

        assert result.success is False
        assert 'Command failed' in result.stderr
        assert result.return_code == -1

    @patch('subprocess.run')
    def test_run_json_success(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"Name": "test"}]',
            stderr=''
        )

        success, data = rclone._run_json('lsjson', 'remote:')

        assert success is True
        assert data == [{'Name': 'test'}]

    @patch('subprocess.run')
    def test_run_json_empty_output(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr=''
        )

        success, data = rclone._run_json('lsjson', 'remote:')

        assert success is True
        assert data == []

    @patch('subprocess.run')
    def test_run_json_invalid_json(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='not valid json',
            stderr=''
        )

        success, data = rclone._run_json('lsjson', 'remote:')

        assert success is False

    @patch('subprocess.run')
    def test_run_json_failure(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='error'
        )

        success, data = rclone._run_json('lsjson', 'remote:')

        assert success is False
        assert data == 'error'

    @patch('subprocess.run')
    def test_version(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='rclone v1.72.1\n- os/version: windows',
            stderr=''
        )

        version = rclone.version()

        assert version == 'rclone v1.72.1'

    @patch('subprocess.run')
    def test_version_failure(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='error'
        )

        version = rclone.version()

        assert version == '未知'

    @patch('subprocess.run')
    def test_listremotes(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='remote1:\nremote2:\n',
            stderr=''
        )

        remotes = rclone.listremotes()

        assert remotes == ['remote1', 'remote2']

    @patch('subprocess.run')
    def test_listremotes_empty(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr=''
        )

        remotes = rclone.listremotes()

        assert remotes == []

    @patch('subprocess.run')
    def test_listremotes_failure(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='error'
        )

        remotes = rclone.listremotes()

        assert remotes == []

    @patch('subprocess.run')
    def test_config_dump(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"remote1": {"type": "webdav"}}',
            stderr=''
        )

        config = rclone.config_dump()

        assert config == {'remote1': {'type': 'webdav'}}

    @patch('subprocess.run')
    def test_config_dump_failure(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='error'
        )

        config = rclone.config_dump()

        assert config == {}

    @patch('subprocess.run')
    def test_config_get(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"myremote": {"type": "sftp", "host": "example.com"}}',
            stderr=''
        )

        config = rclone.config_get('myremote')

        assert config == {'type': 'sftp', 'host': 'example.com'}

    @patch('subprocess.run')
    def test_config_get_not_found(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{}',
            stderr=''
        )

        config = rclone.config_get('nonexistent')

        assert config == {}

    @patch('subprocess.run')
    def test_config_create(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.config_create('newremote', 'webdav', url='https://example.com')

        assert result.success is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'config' in call_args
        assert 'create' in call_args
        assert 'newremote' in call_args
        assert 'webdav' in call_args

    @patch('subprocess.run')
    def test_config_update(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.config_update('myremote', user='newuser')

        assert result.success is True

    @patch('subprocess.run')
    def test_config_delete(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.config_delete('myremote')

        assert result.success is True

    @patch('subprocess.run')
    def test_lsjson(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"Name": "file.txt", "Size": 100}]',
            stderr=''
        )

        success, files = rclone.lsjson('remote:/path')

        assert success is True
        assert files == [{'Name': 'file.txt', 'Size': 100}]

    @patch('subprocess.run')
    def test_lsjson_recursive(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[]',
            stderr=''
        )

        rclone.lsjson('remote:/path', recursive=True)

        call_args = mock_run.call_args[0][0]
        assert '--recursive' in call_args

    @patch('subprocess.run')
    def test_ls(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"Name": "test.txt"}]',
            stderr=''
        )

        files = rclone.ls('remote:/')

        assert files == [{'Name': 'test.txt'}]

    @patch('subprocess.run')
    def test_ls_failure(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='error')

        files = rclone.ls('remote:/')

        assert files == []

    @patch('subprocess.run')
    def test_mkdir(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.mkdir('remote:/newdir')

        assert result.success is True

    @patch('subprocess.run')
    def test_rmdir(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.rmdir('remote:/emptydir')

        assert result.success is True

    @patch('subprocess.run')
    def test_purge(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.purge('remote:/dir')

        assert result.success is True

    @patch('subprocess.run')
    def test_delete_file(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.delete_file('remote:/file.txt')

        assert result.success is True

    @patch('subprocess.run')
    def test_copy(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.copy('/local/path', 'remote:/path')

        assert result.success is True

    @patch('subprocess.run')
    def test_move(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.move('/local/path', 'remote:/path')

        assert result.success is True

    @patch('subprocess.run')
    def test_sync(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.sync('/local/path', 'remote:/path')

        assert result.success is True

    @patch('subprocess.run')
    def test_check(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = rclone.check('myremote')

        assert result.success is True

    @patch('subprocess.run')
    def test_about(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"total": 1000000, "used": 500000}',
            stderr=''
        )

        success, info = rclone.about('myremote')

        assert success is True
        assert info == {'total': 1000000, 'used': 500000}

    @patch('subprocess.run')
    def test_size(self, mock_run, rclone):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"count": 10, "bytes": 1024}',
            stderr=''
        )

        success, info = rclone.size('remote:/path')

        assert success is True
        assert info == {'count': 10, 'bytes': 1024}

    def test_validate_remote_name_empty(self, rclone):
        with pytest.raises(ValueError, match='不能为空'):
            rclone._validate_remote_name('')

    def test_validate_remote_name_invalid(self, rclone):
        with pytest.raises(ValueError, match='非法'):
            rclone._validate_remote_name('test!@#')

    def test_validate_option_key_empty(self, rclone):
        with pytest.raises(ValueError, match='不能为空'):
            rclone._validate_option_key('')

    def test_validate_option_key_invalid(self, rclone):
        with pytest.raises(ValueError, match='非法'):
            rclone._validate_option_key('key!@#')

    def test_sanitize_option_value(self, rclone):
        result = rclone._sanitize_option_value('value; && | cmd')
        assert ';' not in result
        assert '&' not in result
        assert '|' not in result

    def test_sanitize_option_value_none(self, rclone):
        result = rclone._sanitize_option_value(None)
        assert result == ''

    @patch('subprocess.run')
    def test_run_timeout(self, mock_run, rclone):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='rclone', timeout=300)

        result = rclone._run('listremotes')

        assert result.success is False
        assert '超时' in result.stderr
        assert result.return_code == -1

    @patch('subprocess.run')
    def test_run_os_error(self, mock_run, rclone):
        import subprocess
        mock_run.side_effect = OSError('File not found')

        result = rclone._run('listremotes')

        assert result.success is False
        assert '系统错误' in result.stderr
        assert result.return_code == -1

    def test_config_create_invalid_name(self, rclone):
        with pytest.raises(ValueError, match='非法'):
            rclone.config_create('invalid name!', 'webdav')

    @patch('subprocess.run')
    def test_config_create_invalid_option_key(self, mock_run, rclone):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        with pytest.raises(ValueError, match='非法'):
            rclone.config_create('test', 'webdav', **{'invalid key!': 'value'})

    def test_config_update_invalid_name(self, rclone):
        with pytest.raises(ValueError, match='非法'):
            rclone.config_update('invalid name!')

    def test_config_delete_invalid_name(self, rclone):
        with pytest.raises(ValueError, match='非法'):
            rclone.config_delete('invalid name!')
