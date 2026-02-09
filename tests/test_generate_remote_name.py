"""generate_remote_name 的属性测试和单元测试"""
import re
import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from app.views.remote_interface import generate_remote_name
from app.providers import get_all_providers

# --- 属性测试 (任务 1.2) ---

TYPE_DISPLAY_NAMES = [info['name'] for info in get_all_providers().values()]


def _sanitize(name: str) -> str:
    base = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    return base if base else "Remote"


class TestGenerateRemoteNameProperties:

    @given(
        type_name=st.sampled_from(TYPE_DISPLAY_NAMES),
        existing=st.lists(st.sampled_from([
            'WebDAV1', 'WebDAV2', 'WebDAV3', 'SFTP1', 'SFTP2',
            'FTP1', 'SMBCIFS1', 'AmazonS31', 'Remote1', 'myremote',
            'test-1', 'backup_2', 'server3', 'cloud4', 'nas5',
        ]), max_size=10, unique=True)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property1_uniqueness(self, type_name, existing):
        """Property 1: 生成名称的唯一性
        **Validates: Requirements 1.3, 3.1, 3.2**
        """
        result = generate_remote_name(type_name, existing)
        assert result not in existing

    @given(type_name=st.sampled_from(TYPE_DISPLAY_NAMES))
    @settings(max_examples=100)
    def test_property2_format_validity(self, type_name):
        """Property 2: 生成名称的格式合法性
        **Validates: Requirements 1.2, 3.3**
        """
        result = generate_remote_name(type_name, [])
        base = _sanitize(type_name)
        assert result.startswith(base)
        suffix = result[len(base):]
        assert suffix.isdigit()
        assert int(suffix) >= 1
        assert re.match(r'^[a-zA-Z0-9_-]+$', result)


# --- 单元测试 (任务 1.3) ---

class TestGenerateRemoteNameUnit:

    def test_webdav_sanitize(self):
        assert generate_remote_name('WebDAV', []) == 'WebDAV1'

    def test_sftp_sanitize(self):
        assert generate_remote_name('SFTP', []) == 'SFTP1'

    def test_ftp_sanitize(self):
        assert generate_remote_name('FTP', []) == 'FTP1'

    def test_smb_cifs_sanitize(self):
        assert generate_remote_name('SMB / CIFS', []) == 'SMBCIFS1'

    def test_amazon_s3_sanitize(self):
        assert generate_remote_name('Amazon S3', []) == 'AmazonS31'

    def test_increment_on_conflict(self):
        assert generate_remote_name('WebDAV', ['WebDAV1']) == 'WebDAV2'

    def test_increment_skips_multiple(self):
        assert generate_remote_name('WebDAV', ['WebDAV1', 'WebDAV2', 'WebDAV3']) == 'WebDAV4'

    def test_increment_with_gap(self):
        assert generate_remote_name('SFTP', ['SFTP1', 'SFTP3']) == 'SFTP2'

    def test_empty_existing_names(self):
        assert generate_remote_name('WebDAV', []) == 'WebDAV1'

    def test_none_existing_names(self):
        assert generate_remote_name('WebDAV', None) == 'WebDAV1'

    def test_empty_display_name_uses_default(self):
        assert generate_remote_name('', []) == 'Remote1'

    def test_special_chars_only_uses_default(self):
        assert generate_remote_name('/ @#$', []) == 'Remote1'
