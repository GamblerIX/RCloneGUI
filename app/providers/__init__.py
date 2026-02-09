"""
提供商注册表模块（Registry）。

通过 importlib + pkgutil 自动发现 app/providers/ 包下所有提供商模块，
收集含 PROVIDER 属性的模块配置，对外提供统一查询接口。

注意：
- 使用标准 logging 而非 app.common.logger（避免循环导入和 Qt 依赖）
- 缓存使用纯 Python 模块级变量，不依赖 Qt 对象
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)

# 模块级缓存变量（纯 Python，不依赖 Qt 对象）
_providers_cache: dict[str, dict] | None = None

# PROVIDER 字典中必须包含的键
_REQUIRED_KEYS = {'type_id', 'name', 'fields'}


def _discover_providers() -> dict[str, dict]:
    """扫描 app.providers 包下所有模块，收集含 PROVIDER 属性的模块配置。

    扫描规则：
    - 跳过以 '_' 开头的模块（约定为内部模块）
    - 跳过不含 PROVIDER 属性的模块（记录 warning）
    - 跳过 PROVIDER 字典缺少必需键（type_id/name/fields）的模块（记录 warning）
    - 模块导入失败时跳过并记录 error，不影响其他模块
    - type_id 重复时后加载覆盖先加载（记录 warning）
    - 空目录返回空字典，不抛异常

    Returns:
        键为 type_id，值为提供商配置（不含 type_id 键）的字典。
    """
    providers: dict[str, dict] = {}

    package = importlib.import_module('app.providers')

    for _importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        # 跳过以 '_' 开头的内部模块
        if modname.startswith('_'):
            continue

        # 导入模块，失败时跳过并记录 error
        try:
            module = importlib.import_module(f'app.providers.{modname}')
        except Exception:
            logger.error("导入提供商模块 '%s' 失败", modname, exc_info=True)
            continue

        # 检查模块是否含 PROVIDER 属性
        if not hasattr(module, 'PROVIDER'):
            logger.warning("模块 '%s' 缺少 PROVIDER 属性，已跳过", modname)
            continue

        config = module.PROVIDER

        # 验证 PROVIDER 字典包含必需键
        missing_keys = _REQUIRED_KEYS - set(config.keys())
        if missing_keys:
            logger.warning(
                "模块 '%s' 的 PROVIDER 缺少必需键 %s，已跳过",
                modname, missing_keys,
            )
            continue

        type_id = config['type_id']

        # type_id 重复时记录 warning
        if type_id in providers:
            logger.warning(
                "type_id '%s' 重复（模块 '%s'），将覆盖先前的注册",
                type_id, modname,
            )

        # 存储时去掉 type_id 键，保持与原 REMOTE_TYPES 结构一致
        providers[type_id] = {k: v for k, v in config.items() if k != 'type_id'}

    return providers


def get_all_providers() -> dict[str, dict]:
    """返回所有已注册提供商，键为 type_id，值为提供商配置（不含 type_id 键）。

    首次调用时执行自动发现并缓存结果，后续调用直接返回缓存。

    返回格式与原 REMOTE_TYPES 一致：
    {
        'sftp': {'name': 'SFTP', 'fields': {...}},
        's3': {'name': 'Amazon S3', 'fields': {...}, 'provider_config': {...}},
        ...
    }
    """
    global _providers_cache
    if _providers_cache is None:
        _providers_cache = _discover_providers()
    return _providers_cache


def get_provider(type_id: str) -> dict | None:
    """根据 type_id 返回单个提供商配置，未找到返回 None。

    Args:
        type_id: 提供商类型标识，如 'sftp'、's3'。

    Returns:
        提供商配置字典（不含 type_id 键），或 None（未找到时）。
    """
    return get_all_providers().get(type_id)


def _clear_cache() -> None:
    """清除提供商缓存，供测试使用。"""
    global _providers_cache
    _providers_cache = None
