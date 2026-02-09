"""
WebDAV 提供商配置 vendor_config 的属性测试。

包含 Property 7，验证已知 WebDAV 服务商（非 "other"）的 url 配置
同时包含 `fixed_url`（非空字符串）和 `readonly`（值为 True）字段。

Feature: mount-and-vendor-improvements, Property 7: 已知 WebDAV 服务商配置完整性
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.providers.webdav import PROVIDER


# ---------------------------------------------------------------------------
# 智能生成器：从 vendor_config 中选取已知服务商（排除 "other"）
# ---------------------------------------------------------------------------

vendor_config = PROVIDER['vendor_config']

# 已知服务商列表：vendor_config 中 vendor 名称不为 "other" 的条目
known_vendors = [name for name in vendor_config if name != 'other']

# 已知服务商策略：从已知服务商列表中随机选取
known_vendor_names = st.sampled_from(known_vendors)


# ===========================================================================
# Property 7: 已知 WebDAV 服务商配置完整性
# ===========================================================================

# Feature: mount-and-vendor-improvements, Property 7: 已知 WebDAV 服务商配置完整性
class TestProperty7KnownVendorConfigCompleteness:
    """**Validates: Requirements 6.1, 6.2**"""

    @given(vendor_name=known_vendor_names)
    @settings(max_examples=100)
    def test_known_vendor_has_fixed_url_and_readonly(
        self,
        vendor_name: str,
    ) -> None:
        """对于任意已知 WebDAV 服务商，其 url 配置应同时包含
        fixed_url（非空字符串）和 readonly（值为 True）字段。"""
        vcfg = vendor_config[vendor_name]

        # url 配置必须存在
        assert 'url' in vcfg, (
            f"已知服务商 {vendor_name!r} 的配置中缺少 'url' 字段。"
            f"\n实际配置: {vcfg!r}"
        )

        url_cfg = vcfg['url']

        # fixed_url 字段必须存在且为非空字符串
        assert 'fixed_url' in url_cfg, (
            f"已知服务商 {vendor_name!r} 的 url 配置中缺少 'fixed_url' 字段。"
            f"\n实际 url 配置: {url_cfg!r}"
        )
        assert isinstance(url_cfg['fixed_url'], str), (
            f"已知服务商 {vendor_name!r} 的 fixed_url 应为字符串类型，"
            f"实际类型为 {type(url_cfg['fixed_url']).__name__}。"
        )
        assert url_cfg['fixed_url'] != '', (
            f"已知服务商 {vendor_name!r} 的 fixed_url 不应为空字符串。"
        )

        # readonly 字段必须存在且值为 True
        assert 'readonly' in url_cfg, (
            f"已知服务商 {vendor_name!r} 的 url 配置中缺少 'readonly' 字段。"
            f"\n实际 url 配置: {url_cfg!r}"
        )
        assert url_cfg['readonly'] is True, (
            f"已知服务商 {vendor_name!r} 的 readonly 应为 True，"
            f"实际值为 {url_cfg['readonly']!r}。"
        )
