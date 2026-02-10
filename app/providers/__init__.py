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


def _register_provider(config: dict, providers: dict[str, dict], source: str = "") -> None:
    """将单个 PROVIDER 配置注册到 providers 字典中。"""
    missing_keys = _REQUIRED_KEYS - set(config.keys())
    if missing_keys:
        logger.warning("提供商配置缺少必需键 %s（来源: %s），已跳过", missing_keys, source)
        return

    type_id = config['type_id']
    if type_id in providers:
        logger.warning("type_id '%s' 重复（来源: %s），将覆盖先前的注册", type_id, source)
    providers[type_id] = {k: v for k, v in config.items() if k != 'type_id'}


def _discover_dynamic() -> dict[str, dict]:
    """通过 pkgutil 动态扫描发现提供商模块（开发环境）。"""
    providers: dict[str, dict] = {}
    try:
        package = importlib.import_module('app.providers')
        for _importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
            if modname.startswith('_'):
                continue
            try:
                module = importlib.import_module(f'app.providers.{modname}')
            except Exception:
                logger.error("导入提供商模块 '%s' 失败", modname, exc_info=True)
                continue
            if not hasattr(module, 'PROVIDER'):
                logger.warning("模块 '%s' 缺少 PROVIDER 属性，已跳过", modname)
                continue
            _register_provider(module.PROVIDER, providers, source=modname)
    except Exception:
        logger.warning("动态发现提供商模块失败", exc_info=True)
    return providers


def _discover_static() -> dict[str, dict]:
    """通过显式 import 加载所有已知提供商（打包环境 fallback）。

    直接使用 from ... import 而非 importlib.import_module，
    确保 PyInstaller / Nuitka / cx_Freeze 能正确追踪依赖并打包这些模块。
    """
    providers: dict[str, dict] = {}
    # 显式导入每个提供商模块，打包工具会将其识别为静态依赖
    _static_modules: list[tuple[str, object | None]] = []
    try:
        from app.providers import ftp as _ftp
        _static_modules.append(('ftp', _ftp))
    except Exception:
        logger.error("显式导入 ftp 失败", exc_info=True)
    try:
        from app.providers import sftp as _sftp
        _static_modules.append(('sftp', _sftp))
    except Exception:
        logger.error("显式导入 sftp 失败", exc_info=True)
    try:
        from app.providers import s3 as _s3
        _static_modules.append(('s3', _s3))
    except Exception:
        logger.error("显式导入 s3 失败", exc_info=True)
    try:
        from app.providers import smb as _smb
        _static_modules.append(('smb', _smb))
    except Exception:
        logger.error("显式导入 smb 失败", exc_info=True)
    try:
        from app.providers import webdav as _webdav
        _static_modules.append(('webdav', _webdav))
    except Exception:
        logger.error("显式导入 webdav 失败", exc_info=True)

    for modname, module in _static_modules:
        if hasattr(module, 'PROVIDER'):
            _register_provider(module.PROVIDER, providers, source=f'{modname}(static)')

    return providers


def _discover_providers() -> dict[str, dict]:
    """发现并注册所有提供商。

    优先使用 pkgutil 动态扫描（开发环境），若结果为空则回退到
    显式 import（打包环境）。
    """
    providers = _discover_dynamic()

    if not providers:
        logger.info("动态发现未找到提供商，回退到显式导入（可能处于打包环境）")
        providers = _discover_static()

    logger.info("共注册 %d 个提供商: %s", len(providers), list(providers.keys()))
    return providers


def get_all_providers() -> dict[str, dict]:
    """返回所有已注册提供商，键为 type_id，值为提供商配置（不含 type_id 键）。

    首次调用时执行自动发现并缓存结果，后续调用直接返回缓存。
    """
    global _providers_cache
    if _providers_cache is None:
        _providers_cache = _discover_providers()
    return _providers_cache


def get_provider(type_id: str) -> dict | None:
    """根据 type_id 返回单个提供商配置，未找到返回 None。"""
    return get_all_providers().get(type_id)


def _clear_cache() -> None:
    """清除提供商缓存，供测试使用。"""
    global _providers_cache
    _providers_cache = None
