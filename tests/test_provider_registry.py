"""
提供商注册表（Provider Registry）属性测试与单元测试。

包含 5 个属性测试（Property 1-5）和单元测试，验证 Registry 模块的正确性。
"""

import json
import importlib

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.providers import get_all_providers, get_provider, _clear_cache


# ---------------------------------------------------------------------------
# 辅助数据：收集所有已注册提供商的 type_id 列表和原始 PROVIDER 字典
# ---------------------------------------------------------------------------

# 收集各模块的原始 PROVIDER 字典（含 type_id）
_PROVIDER_MODULES = ['webdav', 'sftp', 'ftp', 'smb', 's3']
_RAW_PROVIDERS: list[dict] = []
for _mod_name in _PROVIDER_MODULES:
    _mod = importlib.import_module(f'app.providers.{_mod_name}')
    _RAW_PROVIDERS.append(_mod.PROVIDER)

# 已注册的 type_id 列表（从 Registry 获取）
_clear_cache()
_REGISTERED_TYPE_IDS: list[str] = list(get_all_providers().keys())

# 合法的字段类型
_VALID_FIELD_TYPES = {'text', 'password', 'choice', 'number', 'bool', 'file'}


# ===========================================================================
# Property 1：提供商配置结构有效性
# ===========================================================================

# Feature: provider-registry, Property 1: 提供商配置结构有效性
class TestProperty1ProviderConfigStructure:
    """**Validates: Requirements 1.1, 1.4**"""

    @given(provider=st.sampled_from(_RAW_PROVIDERS))
    @settings(max_examples=100)
    def test_provider_has_required_keys(self, provider: dict) -> None:
        """每个原始 PROVIDER 字典必须包含 type_id（字符串）、name（字符串）、fields（字典）。"""
        _clear_cache()

        # 验证必需键存在
        assert 'type_id' in provider, "PROVIDER 缺少 'type_id' 键"
        assert 'name' in provider, "PROVIDER 缺少 'name' 键"
        assert 'fields' in provider, "PROVIDER 缺少 'fields' 键"

        # 验证类型
        assert isinstance(provider['type_id'], str), "type_id 必须是字符串"
        assert isinstance(provider['name'], str), "name 必须是字符串"
        assert isinstance(provider['fields'], dict), "fields 必须是字典"

    @given(provider=st.sampled_from(_RAW_PROVIDERS))
    @settings(max_examples=100)
    def test_field_definitions_have_required_attributes(self, provider: dict) -> None:
        """每个字段定义必须包含 label（字符串）、required（布尔值）、type（合法取值）。"""
        _clear_cache()

        fields = provider['fields']
        for field_name, field_def in fields.items():
            assert 'label' in field_def, f"字段 '{field_name}' 缺少 'label'"
            assert 'required' in field_def, f"字段 '{field_name}' 缺少 'required'"
            assert 'type' in field_def, f"字段 '{field_name}' 缺少 'type'"

            assert isinstance(field_def['label'], str), \
                f"字段 '{field_name}' 的 label 必须是字符串"
            assert isinstance(field_def['required'], bool), \
                f"字段 '{field_name}' 的 required 必须是布尔值"
            assert field_def['type'] in _VALID_FIELD_TYPES, \
                f"字段 '{field_name}' 的 type '{field_def['type']}' 不在合法取值中"


# ===========================================================================
# Property 2：注册表输出等价性
# ===========================================================================

# 构建期望输出：从各提供商模块的原始 PROVIDER 字典中提取
_EXPECTED_PROVIDERS: dict[str, dict] = {}
for _mod_name in _PROVIDER_MODULES:
    _mod = importlib.import_module(f'app.providers.{_mod_name}')
    _p = _mod.PROVIDER
    _EXPECTED_PROVIDERS[_p['type_id']] = {k: v for k, v in _p.items() if k != 'type_id'}

# Feature: provider-registry, Property 2: 注册表输出等价性
class TestProperty2RegistryOutputEquivalence:
    """**Validates: Requirements 2.2, 6.1**"""

    @given(type_id=st.sampled_from(_REGISTERED_TYPE_IDS))
    @settings(max_examples=100)
    def test_registry_output_matches_raw_providers(self, type_id: str) -> None:
        """Registry 通过 get_all_providers() 收集的配置与各模块原始 PROVIDER 字典完全等价。"""
        _clear_cache()

        all_providers = get_all_providers()
        assert type_id in all_providers, f"Registry 缺少 type_id '{type_id}'"
        assert type_id in _EXPECTED_PROVIDERS, f"期望数据缺少 type_id '{type_id}'"
        assert all_providers[type_id] == _EXPECTED_PROVIDERS[type_id], \
            f"type_id '{type_id}' 的 Registry 输出与原始 PROVIDER 字典不一致"


# ===========================================================================
# Property 3：get_provider 与 get_all_providers 一致性
# ===========================================================================

# Feature: provider-registry, Property 3: get_provider 与 get_all_providers 一致性
class TestProperty3GetProviderConsistency:
    """**Validates: Requirements 3.2**"""

    @given(type_id=st.sampled_from(_REGISTERED_TYPE_IDS))
    @settings(max_examples=100)
    def test_get_provider_matches_get_all_providers(self, type_id: str) -> None:
        """get_provider(type_id) 返回的配置与 get_all_providers()[type_id] 完全相同。"""
        _clear_cache()

        single = get_provider(type_id)
        all_providers = get_all_providers()

        assert single is not None, f"get_provider('{type_id}') 不应返回 None"
        assert single == all_providers[type_id], \
            f"get_provider('{type_id}') 与 get_all_providers()['{type_id}'] 不一致"


# ===========================================================================
# Property 4：未注册 type_id 返回 None
# ===========================================================================

# Feature: provider-registry, Property 4: 未注册 type_id 返回 None
class TestProperty4UnregisteredTypeIdReturnsNone:
    """**Validates: Requirements 3.3**"""

    @given(type_id=st.text(min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_unregistered_type_id_returns_none(self, type_id: str) -> None:
        """不在已注册提供商列表中的字符串，get_provider 应返回 None。"""
        _clear_cache()

        # 过滤掉已注册的 type_id
        assume(type_id not in _REGISTERED_TYPE_IDS)

        result = get_provider(type_id)
        assert result is None, \
            f"get_provider('{type_id}') 应返回 None，但返回了 {result}"


# ===========================================================================
# Property 5：提供商配置 JSON 序列化往返
# ===========================================================================

# Feature: provider-registry, Property 5: 提供商配置 JSON 序列化往返
class TestProperty5JsonRoundTrip:
    """**Validates: Requirements 6.2**"""

    @given(type_id=st.sampled_from(_REGISTERED_TYPE_IDS))
    @settings(max_examples=100)
    def test_json_serialization_round_trip(self, type_id: str) -> None:
        """提供商配置序列化为 JSON 再反序列化，应与原始配置等价。"""
        _clear_cache()

        config = get_provider(type_id)
        assert config is not None

        serialized = json.dumps(config, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert deserialized == config, \
            f"type_id '{type_id}' 的 JSON 序列化往返不等价"


# ===========================================================================
# 单元测试
# ===========================================================================

class TestProviderModulesImportable:
    """验证每个提供商模块可导入。"""

    @pytest.mark.parametrize("module_name", _PROVIDER_MODULES)
    def test_module_importable(self, module_name: str) -> None:
        """_Requirements: 2.1_"""
        mod = importlib.import_module(f'app.providers.{module_name}')
        assert hasattr(mod, 'PROVIDER'), f"模块 '{module_name}' 缺少 PROVIDER 属性"

    @pytest.mark.parametrize("module_name", _PROVIDER_MODULES)
    def test_module_provider_has_type_id(self, module_name: str) -> None:
        """_Requirements: 1.1_"""
        mod = importlib.import_module(f'app.providers.{module_name}')
        provider = mod.PROVIDER
        assert 'type_id' in provider
        assert provider['type_id'] == module_name


class TestWebDAVVendorConfig:
    """验证 WebDAV 含 vendor_config。"""

    def test_webdav_has_vendor_config(self) -> None:
        """_Requirements: 1.2_"""
        from app.providers.webdav import PROVIDER
        assert 'vendor_config' in PROVIDER, "WebDAV PROVIDER 缺少 vendor_config"
        assert isinstance(PROVIDER['vendor_config'], dict)
        assert len(PROVIDER['vendor_config']) > 0, "vendor_config 不应为空"


class TestS3ProviderConfig:
    """验证 S3 含 provider_config。"""

    def test_s3_has_provider_config(self) -> None:
        """_Requirements: 1.3_"""
        from app.providers.s3 import PROVIDER
        assert 'provider_config' in PROVIDER, "S3 PROVIDER 缺少 provider_config"
        assert isinstance(PROVIDER['provider_config'], dict)
        assert len(PROVIDER['provider_config']) > 0, "provider_config 不应为空"


class TestEmptyDirectoryReturnsEmptyDict:
    """验证空目录返回空字典。"""

    def test_empty_providers_directory(self, monkeypatch) -> None:
        """_Requirements: 3.5_"""
        _clear_cache()

        # 模拟 pkgutil.iter_modules 返回空列表，模拟空目录
        import app.providers as providers_pkg
        monkeypatch.setattr(
            'pkgutil.iter_modules',
            lambda path: iter([]),
        )

        _clear_cache()
        result = get_all_providers()
        assert result == {}, f"空目录应返回空字典，但返回了 {result}"

        # 清理：恢复缓存以免影响后续测试
        _clear_cache()


class TestRegistryErrorHandling:
    """验证 Registry 的所有错误处理路径。

    _Requirements: 7.3_
    覆盖 app/providers/__init__.py 中未覆盖的错误处理分支：
    - 模块导入失败（语法错误、依赖缺失）
    - 模块缺少 PROVIDER 属性
    - PROVIDER 字典缺少必需键（type_id/name/fields）
    - type_id 重复（后加载覆盖先加载）
    """

    def test_module_import_failure(self, monkeypatch) -> None:
        """模块导入失败时，Registry 跳过该模块并记录 error，不影响其他模块加载。"""
        import types

        _clear_cache()

        fake_modules = [
            (None, 'broken_module', False),
            (None, 'sftp', False),
        ]
        monkeypatch.setattr(
            'pkgutil.iter_modules',
            lambda path: iter(fake_modules),
        )

        original_import = importlib.import_module

        def patched_import(name, *args, **kwargs):
            if name == 'app.providers.broken_module':
                raise SyntaxError("模拟语法错误")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr('importlib.import_module', patched_import)

        _clear_cache()
        result = get_all_providers()

        # broken_module 被跳过，sftp 正常加载
        assert 'sftp' in result, "sftp 应正常加载"
        assert 'broken_module' not in result

        _clear_cache()

    def test_module_missing_provider_attribute(self, monkeypatch) -> None:
        """模块缺少 PROVIDER 属性时，Registry 跳过该模块并记录 warning。"""
        import types

        _clear_cache()

        fake_module = types.ModuleType('app.providers.no_provider_mod')

        fake_modules = [
            (None, 'no_provider_mod', False),
            (None, 'sftp', False),
        ]
        monkeypatch.setattr(
            'pkgutil.iter_modules',
            lambda path: iter(fake_modules),
        )

        original_import = importlib.import_module

        def patched_import(name, *args, **kwargs):
            if name == 'app.providers.no_provider_mod':
                return fake_module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr('importlib.import_module', patched_import)

        _clear_cache()
        result = get_all_providers()

        # no_provider_mod 被跳过，sftp 正常加载
        assert 'sftp' in result
        assert len([k for k in result if k not in _REGISTERED_TYPE_IDS]) == 0

        _clear_cache()

    def test_provider_missing_required_keys(self, monkeypatch) -> None:
        """PROVIDER 字典缺少必需键时，Registry 跳过该模块并记录 warning。"""
        import types

        _clear_cache()

        fake_module = types.ModuleType('app.providers.bad_keys_mod')
        fake_module.PROVIDER = {
            'type_id': 'bad_keys',
            'name': 'Bad Keys Provider',
            # 缺少 'fields' 键
        }

        fake_modules = [
            (None, 'bad_keys_mod', False),
            (None, 'sftp', False),
        ]
        monkeypatch.setattr(
            'pkgutil.iter_modules',
            lambda path: iter(fake_modules),
        )

        original_import = importlib.import_module

        def patched_import(name, *args, **kwargs):
            if name == 'app.providers.bad_keys_mod':
                return fake_module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr('importlib.import_module', patched_import)

        _clear_cache()
        result = get_all_providers()

        # bad_keys_mod 被跳过
        assert 'bad_keys' not in result
        # sftp 正常加载
        assert 'sftp' in result

        _clear_cache()

    def test_underscore_prefixed_module_skipped(self, monkeypatch) -> None:
        """以 '_' 开头的模块应被跳过，不参与提供商注册。"""
        _clear_cache()

        fake_modules = [
            (None, '_internal_mod', False),
            (None, 'sftp', False),
        ]
        monkeypatch.setattr(
            'pkgutil.iter_modules',
            lambda path: iter(fake_modules),
        )

        original_import = importlib.import_module

        def patched_import(name, *args, **kwargs):
            if name == 'app.providers._internal_mod':
                raise AssertionError("不应尝试导入以 '_' 开头的模块")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr('importlib.import_module', patched_import)

        _clear_cache()
        result = get_all_providers()

        # _internal_mod 被跳过，sftp 正常加载
        assert 'sftp' in result

        _clear_cache()

    def test_duplicate_type_id_overwrites(self, monkeypatch) -> None:
        """type_id 重复时，后加载的模块覆盖先加载的，并记录 warning。"""
        import types

        _clear_cache()

        fake_mod_first = types.ModuleType('app.providers.dup_first')
        fake_mod_first.PROVIDER = {
            'type_id': 'dup_test',
            'name': 'First Provider',
            'fields': {'host': {'label': '主机', 'required': True, 'type': 'text'}},
        }

        fake_mod_second = types.ModuleType('app.providers.dup_second')
        fake_mod_second.PROVIDER = {
            'type_id': 'dup_test',
            'name': 'Second Provider',
            'fields': {'host': {'label': '主机地址', 'required': True, 'type': 'text'}},
        }

        fake_modules = [
            (None, 'dup_first', False),
            (None, 'dup_second', False),
        ]
        monkeypatch.setattr(
            'pkgutil.iter_modules',
            lambda path: iter(fake_modules),
        )

        original_import = importlib.import_module

        def patched_import(name, *args, **kwargs):
            if name == 'app.providers.dup_first':
                return fake_mod_first
            if name == 'app.providers.dup_second':
                return fake_mod_second
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr('importlib.import_module', patched_import)

        _clear_cache()
        result = get_all_providers()

        # 后加载的 dup_second 覆盖 dup_first
        assert 'dup_test' in result
        assert result['dup_test']['name'] == 'Second Provider'

        _clear_cache()

