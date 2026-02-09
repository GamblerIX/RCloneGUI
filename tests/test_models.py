import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


class TestRemote:

    def test_remote_creation(self):
        from app.models.remote import Remote

        remote = Remote(
            name='test_remote',
            type='s3',
            config={'region': 'us-east-1'}
        )

        assert remote.name == 'test_remote'
        assert remote.type == 's3'
        assert remote.config == {'region': 'us-east-1'}

    def test_remote_default_config(self):
        from app.models.remote import Remote

        remote = Remote(name='test', type='s3')

        assert remote.config == {}

    def test_remote_validation_empty_name(self):
        from app.models.remote import Remote

        with pytest.raises(ValueError, match='不能为空'):
            Remote(name='', type='s3')

    def test_remote_validation_invalid_name(self):
        from app.models.remote import Remote

        with pytest.raises(ValueError, match='无效的远程存储名称'):
            Remote(name='test remote!', type='s3')

    def test_remote_validation_empty_type(self):
        from app.models.remote import Remote

        with pytest.raises(ValueError, match='不能为空'):
            Remote(name='test', type='')

    def test_remote_host_property(self):
        from app.models.remote import Remote

        remote = Remote(name='test', type='sftp', config={'host': 'example.com'})
        assert remote.host == 'example.com'

        remote = Remote(name='test', type='webdav', config={'url': 'http://example.com'})
        assert remote.host == 'http://example.com'

    def test_remote_user_property(self):
        from app.models.remote import Remote

        remote = Remote(name='test', type='sftp', config={'user': 'admin'})
        assert remote.user == 'admin'

        remote = Remote(name='test', type='sftp', config={'username': 'root'})
        assert remote.user == 'root'

    def test_remote_to_dict(self):
        from app.models.remote import Remote

        remote = Remote(
            name='test_remote',
            type='s3',
            config={'region': 'us-east-1'}
        )

        data = remote.to_dict()

        assert data['name'] == 'test_remote'
        assert data['type'] == 's3'
        assert data['config'] == {'region': 'us-east-1'}

    def test_remote_from_dict(self):
        from app.models.remote import Remote

        data = {
            'name': 'test_remote',
            'type': 's3',
            'config': {'region': 'us-east-1'}
        }

        remote = Remote.from_dict(data)

        assert remote.name == 'test_remote'
        assert remote.type == 's3'
        assert remote.config == {'region': 'us-east-1'}

    def test_remote_from_dict_missing_name(self):
        from app.models.remote import Remote

        data = {'type': 's3'}

        with pytest.raises(KeyError, match='name'):
            Remote.from_dict(data)

    def test_remote_from_dict_missing_type(self):
        from app.models.remote import Remote

        data = {'name': 'test'}

        with pytest.raises(KeyError, match='type'):
            Remote.from_dict(data)

    def test_remote_str(self):
        from app.models.remote import Remote

        remote = Remote(name='test', type='s3')
        assert str(remote) == 'test (s3)'

    def test_remote_eq(self):
        from app.models.remote import Remote

        remote1 = Remote(name='test', type='s3')
        remote2 = Remote(name='test', type='webdav')
        remote3 = Remote(name='other', type='s3')

        assert remote1 == remote2
        assert remote1 != remote3
        assert remote1 != 'test'

    def test_remote_hash(self):
        from app.models.remote import Remote

        remote = Remote(name='test', type='s3')
        assert hash(remote) == hash('test')


class TestMount:

    def test_mount_creation(self):
        from app.models.mount import Mount, MountStatus

        mount = Mount(
            remote_name='test_remote',
            remote_path='/path',
            drive_letter='Z',
            status=MountStatus.MOUNTED,
            auto_mount=True
        )

        assert mount.remote_name == 'test_remote'
        assert mount.remote_path == '/path'
        assert mount.drive_letter == 'Z'
        assert mount.status == MountStatus.MOUNTED
        assert mount.auto_mount is True

    def test_mount_default_values(self):
        from app.models.mount import Mount, MountStatus

        mount = Mount(remote_name='test', remote_path='', drive_letter='Z')

        assert mount.status == MountStatus.UNMOUNTED
        assert mount.auto_mount is False
        assert mount.read_only is False
        assert mount.cache_mode == 'off'
        assert mount.vfs_cache_max_size == '10G'
        assert mount.process_id is None
        assert mount.error_message is None

    def test_mount_validation_invalid_drive_letter(self):
        from app.models.mount import Mount

        with pytest.raises(ValueError, match='Invalid drive letter'):
            Mount(remote_name='test', remote_path='', drive_letter='')

        with pytest.raises(ValueError, match='Invalid drive letter'):
            Mount(remote_name='test', remote_path='', drive_letter='AB')

    def test_mount_validation_invalid_cache_mode(self):
        from app.models.mount import Mount

        with pytest.raises(ValueError, match='Invalid cache_mode'):
            Mount(remote_name='test', remote_path='', drive_letter='Z', cache_mode='invalid')

    def test_mount_validation_invalid_cache_size(self):
        from app.models.mount import Mount

        with pytest.raises(ValueError, match='Invalid vfs_cache_max_size'):
            Mount(remote_name='test', remote_path='', drive_letter='Z', vfs_cache_max_size='invalid')

    def test_mount_remote_full_path(self):
        from app.models.mount import Mount

        mount = Mount(remote_name='test', remote_path='/folder', drive_letter='Z')
        assert mount.remote_full_path == 'test:folder'

        mount = Mount(remote_name='test', remote_path='', drive_letter='Z')
        assert mount.remote_full_path == 'test:'

    def test_mount_is_mounted_windows(self):
        from app.models.mount import Mount, MountStatus

        mount = Mount(remote_name='test', remote_path='', drive_letter='Z')

        with patch('os.name', 'nt'):
            with patch('os.path.exists', return_value=True):
                assert mount.is_mounted is True

    def test_mount_is_mounted_windows_not_exists(self):
        from app.models.mount import Mount, MountStatus

        mount = Mount(remote_name='test', remote_path='', drive_letter='Z')

        with patch('os.name', 'nt'):
            with patch('os.path.exists', return_value=False):
                assert mount.is_mounted is False

    def test_mount_is_mounted_posix(self):
        from app.models.mount import Mount, MountStatus

        mount = Mount(remote_name='test', remote_path='', drive_letter='Z', status=MountStatus.MOUNTED)

        with patch('os.name', 'posix'):
            assert mount.is_mounted is True

    def test_mount_check_drive_exists_non_windows(self):
        from app.models.mount import Mount

        mount = Mount(remote_name='test', remote_path='', drive_letter='Z')

        with patch('os.name', 'posix'):
            assert mount.check_drive_exists() is False

    def test_mount_refresh_status(self):
        from app.models.mount import Mount, MountStatus

        mount = Mount(remote_name='test', remote_path='', drive_letter='Z', status=MountStatus.UNMOUNTED)

        with patch('os.name', 'nt'):
            with patch('os.path.exists', return_value=True):
                result = mount.refresh_status()
                assert result is True
                assert mount.status == MountStatus.MOUNTED

    def test_mount_to_dict(self):
        from app.models.mount import Mount, MountStatus

        mount = Mount(
            remote_name='test_remote',
            remote_path='/path',
            drive_letter='Z',
            status=MountStatus.MOUNTED,
            auto_mount=True,
            read_only=True,
            cache_mode='full',
            vfs_cache_max_size='20G',
            process_id=1234,
            error_message='Test error'
        )

        data = mount.to_dict()

        assert data['remote_name'] == 'test_remote'
        assert data['remote_path'] == '/path'
        assert data['drive_letter'] == 'Z'
        assert data['status'] == 'mounted'
        assert data['auto_mount'] is True
        assert data['read_only'] is True
        assert data['cache_mode'] == 'full'
        assert data['vfs_cache_max_size'] == '20G'
        assert data['process_id'] == 1234
        assert data['error_message'] == 'Test error'

    def test_mount_from_dict(self):
        from app.models.mount import Mount, MountStatus

        data = {
            'remote_name': 'test_remote',
            'remote_path': '/path',
            'drive_letter': 'Z',
            'status': 'mounted',
            'auto_mount': True
        }

        mount = Mount.from_dict(data)

        assert mount.remote_name == 'test_remote'
        assert mount.status == MountStatus.MOUNTED
        assert mount.auto_mount is True

    def test_mount_from_dict_invalid_status(self):
        from app.models.mount import Mount, MountStatus

        data = {
            'remote_name': 'test',
            'drive_letter': 'Z',
            'status': 'invalid_status'
        }

        mount = Mount.from_dict(data)
        assert mount.status == MountStatus.UNMOUNTED

    def test_mount_eq(self):
        from app.models.mount import Mount

        mount1 = Mount(remote_name='test', remote_path='', drive_letter='Z')
        mount2 = Mount(remote_name='test', remote_path='/other', drive_letter='Z')
        mount3 = Mount(remote_name='test', remote_path='', drive_letter='Y')

        assert mount1 == mount2
        assert mount1 != mount3
        assert mount1 != 'test'

    def test_mount_hash(self):
        from app.models.mount import Mount

        mount = Mount(remote_name='test', remote_path='', drive_letter='Z')
        assert hash(mount) == hash(('test', 'Z'))

    # ---- Mount 模型扩展：source 字段与 from_process_info 单元测试 ----
    # Requirements: 4.1, 4.2, 4.3

    def test_mount_source_default_is_config(self):
        """未指定 source 时，默认值应为 'config'。"""
        from app.models.mount import Mount

        mount = Mount(remote_name='myremote', remote_path='', drive_letter='Z')
        assert mount.source == "config"

    def test_from_process_info_creates_correct_attributes(self):
        """from_process_info 应创建 source='discovered'、status=MOUNTED 的 Mount，
        并正确设置 drive_letter 和 process_id。"""
        from app.models.mount import Mount, MountStatus

        mount = Mount.from_process_info(drive_letter='X', process_id=9876, remote_name='mycloud')

        assert mount.source == "discovered"
        assert mount.status == MountStatus.MOUNTED
        assert mount.drive_letter == 'X'
        assert mount.process_id == 9876
        assert mount.remote_name == 'mycloud'
        assert mount.remote_path == ''

    def test_from_process_info_empty_remote_name_uses_placeholder(self):
        """from_process_info 未提供 remote_name 时，应使用 'unknown_{drive_letter}' 占位名。"""
        from app.models.mount import Mount

        mount = Mount.from_process_info(drive_letter='D', process_id=1111)
        assert mount.remote_name == 'unknown_D'

    def test_from_process_info_with_provided_remote_name(self):
        """from_process_info 提供了 remote_name 时，应使用该名称。"""
        from app.models.mount import Mount

        mount = Mount.from_process_info(drive_letter='E', process_id=2222, remote_name='onedrive')
        assert mount.remote_name == 'onedrive'

    def test_to_dict_returns_none_for_discovered_mount(self):
        """source='discovered' 的 Mount，to_dict() 应返回 None（不持久化）。"""
        from app.models.mount import Mount, MountStatus

        mount = Mount.from_process_info(drive_letter='F', process_id=3333)
        result = mount.to_dict()
        assert result is None

    def test_to_dict_returns_valid_dict_for_config_mount(self):
        """source='config' 的 Mount，to_dict() 应返回包含 source 字段的有效字典。"""
        from app.models.mount import Mount

        mount = Mount(remote_name='gdrive', remote_path='/docs', drive_letter='G')
        result = mount.to_dict()

        assert isinstance(result, dict)
        assert result['remote_name'] == 'gdrive'
        assert result['remote_path'] == '/docs'
        assert result['drive_letter'] == 'G'
        assert result['source'] == 'config'

    def test_from_dict_reads_source_field(self):
        """from_dict() 应正确读取字典中的 source 字段。"""
        from app.models.mount import Mount

        data = {
            'remote_name': 'testremote',
            'drive_letter': 'H',
            'source': 'discovered',
        }
        mount = Mount.from_dict(data)
        assert mount.source == 'discovered'

    def test_from_dict_defaults_source_to_config(self):
        """from_dict() 在字典中无 source 字段时，应默认为 'config'。"""
        from app.models.mount import Mount

        data = {
            'remote_name': 'oldremote',
            'drive_letter': 'I',
        }
        mount = Mount.from_dict(data)
        assert mount.source == 'config'


class TestSyncTask:

    def test_sync_task_creation(self):
        from app.models.sync_task import SyncTask, SyncMode, SyncStatus

        task = SyncTask(
            name='Test Task',
            source='/local',
            destination='remote:/backup',
            mode=SyncMode.SYNC
        )

        assert task.name == 'Test Task'
        assert task.source == '/local'
        assert task.destination == 'remote:/backup'
        assert task.mode == SyncMode.SYNC
        assert task.status == SyncStatus.IDLE
        assert task.progress == 0

    def test_sync_task_default_values(self):
        from app.models.sync_task import SyncTask, SyncMode, SyncStatus

        task = SyncTask(name='Test')

        assert task.source == ''
        assert task.destination == ''
        assert task.mode == SyncMode.SYNC
        assert task.status == SyncStatus.IDLE
        assert task.progress == 0
        assert task.delete_excluded is False
        assert task.dry_run is False
        assert task.bandwidth_limit == ''
        assert task.exclude_patterns == []
        assert task.scheduled is False
        assert task.cron_expression == ''

    def test_sync_task_validation_invalid_progress(self):
        from app.models.sync_task import SyncTask

        task = SyncTask(name='Test', _progress=150)
        assert task.progress == 100

        task = SyncTask(name='Test', _progress=-10)
        assert task.progress == 0

    def test_sync_task_progress_setter(self):
        from app.models.sync_task import SyncTask

        task = SyncTask(name='Test')

        task.progress = 50
        assert task.progress == 50

        with pytest.raises(TypeError):
            task.progress = 'invalid'

        with pytest.raises(ValueError):
            task.progress = 150

    def test_sync_task_to_dict(self):
        from app.models.sync_task import SyncTask, SyncMode, SyncStatus
        from datetime import datetime

        task = SyncTask(
            name='Test Task',
            source='/local',
            destination='remote:/backup',
            mode=SyncMode.SYNC,
            status=SyncStatus.RUNNING
        )
        task.progress = 50
        task.last_run = datetime(2024, 1, 1, 12, 0, 0)
        task.files_transferred = 100
        task.bytes_transferred = 1024
        task.error_message = 'Test error'

        data = task.to_dict()

        assert data['name'] == 'Test Task'
        assert data['source'] == '/local'
        assert data['destination'] == 'remote:/backup'
        assert data['mode'] == 'sync'
        assert data['status'] == 'running'
        assert data['progress'] == 50
        assert data['last_run'] == '2024-01-01T12:00:00'
        assert data['files_transferred'] == 100
        assert data['bytes_transferred'] == 1024
        assert data['error_message'] == 'Test error'

    def test_sync_task_from_dict(self):
        from app.models.sync_task import SyncTask, SyncMode, SyncStatus

        data = {
            'id': 'test-id',
            'name': 'Test Task',
            'source': '/local',
            'destination': 'remote:/backup',
            'mode': 'sync',
            'status': 'running',
            'progress': 50
        }

        task = SyncTask.from_dict(data)

        assert task.id == 'test-id'
        assert task.name == 'Test Task'
        assert task.mode == SyncMode.SYNC
        assert task.status == SyncStatus.RUNNING
        assert task.progress == 50

    def test_sync_task_from_dict_invalid_mode(self):
        from app.models.sync_task import SyncTask

        data = {
            'name': 'Test',
            'mode': 'invalid_mode'
        }

        with pytest.raises(ValueError, match='Invalid sync mode'):
            SyncTask.from_dict(data)

    def test_sync_task_from_dict_invalid_status(self):
        from app.models.sync_task import SyncTask

        data = {
            'name': 'Test',
            'status': 'invalid_status'
        }

        with pytest.raises(ValueError, match='Invalid sync status'):
            SyncTask.from_dict(data)

    def test_sync_task_from_dict_invalid_last_run(self):
        from app.models.sync_task import SyncTask

        data = {
            'name': 'Test',
            'last_run': 'invalid_date'
        }

        task = SyncTask.from_dict(data)
        assert task.last_run is None

    def test_sync_task_eq(self):
        from app.models.sync_task import SyncTask

        task1 = SyncTask(id='test-id', name='Task 1')
        task2 = SyncTask(id='test-id', name='Task 2')
        task3 = SyncTask(id='other-id', name='Task 1')

        assert task1 == task2
        assert task1 != task3
        assert task1 != 'test-id'

    def test_sync_task_hash(self):
        from app.models.sync_task import SyncTask

        task = SyncTask(id='test-id', name='Test')
        assert hash(task) == hash('test-id')
