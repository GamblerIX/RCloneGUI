from typing import List, Dict, Optional

from .rclone import RClone
from ..common.logger import get_logger
from ..models.remote import Remote

logger = get_logger('config_manager')


class ConfigManager:

    def __init__(self, rclone: Optional[RClone] = None):
        self.rclone = rclone or RClone()
        self._remotes_cache: Dict[str, Remote] = {}
        logger.debug('[ConfigManager] 初始化完成')

    def refresh(self):
        logger.info('[ConfigManager] 刷新远程存储配置缓存')
        self._remotes_cache.clear()
        config_dump = self.rclone.config_dump()
        logger.info(f'[ConfigManager] config_dump 返回 {len(config_dump)} 个配置')

        for name, config in config_dump.items():
            remote_type = config.get('type', 'unknown')
            self._remotes_cache[name] = Remote(
                name=name,
                type=remote_type,
                config=config
            )
            logger.debug(f'[ConfigManager] 缓存远程存储: {name} (type={remote_type})')

    def list_remotes(self) -> List[Remote]:
        if not self._remotes_cache:
            self.refresh()
        logger.debug(f'[ConfigManager] list_remotes: 返回 {len(self._remotes_cache)} 个')
        return list(self._remotes_cache.values())

    def get_remote(self, name: str) -> Optional[Remote]:
        if not self._remotes_cache:
            self.refresh()
        remote = self._remotes_cache.get(name)
        if remote:
            logger.debug(f'[ConfigManager] get_remote({name}): 找到, type={remote.type}')
        else:
            logger.warning(f'[ConfigManager] get_remote({name}): 未找到')
        return remote

    def add_remote(self, name: str, remote_type: str, **options) -> bool:
        safe_opts = {k: ('***' if 'pass' in k or 'secret' in k or 'token' in k else v)
                    for k, v in options.items()}
        logger.info(f'[ConfigManager] add_remote: name={name}, type={remote_type}, options={safe_opts}')

        result = self.rclone.config_create(name, remote_type, **options)
        if result.success:
            logger.info(f'[ConfigManager] add_remote 成功: {name}')
            self._remotes_cache[name] = Remote(
                name=name,
                type=remote_type,
                config=options
            )
        else:
            logger.error(f'[ConfigManager] add_remote 失败: {name}, '
                        f'return_code={result.return_code}, stderr={result.stderr[:300] if result.stderr else "N/A"}')
        return result.success

    def update_remote(self, name: str, **options) -> bool:
        safe_opts = {k: ('***' if 'pass' in k or 'secret' in k or 'token' in k else v)
                    for k, v in options.items()}
        logger.info(f'[ConfigManager] update_remote: name={name}, options={safe_opts}')

        result = self.rclone.config_update(name, **options)
        if result.success:
            logger.info(f'[ConfigManager] update_remote 成功: {name}')
            if name in self._remotes_cache:
                self._remotes_cache[name].config.update(options)
        else:
            logger.error(f'[ConfigManager] update_remote 失败: {name}, '
                        f'return_code={result.return_code}, stderr={result.stderr[:300] if result.stderr else "N/A"}')
        return result.success

    def delete_remote(self, name: str) -> bool:
        logger.info(f'[ConfigManager] delete_remote: name={name}')
        result = self.rclone.config_delete(name)
        if result.success:
            logger.info(f'[ConfigManager] delete_remote 成功: {name}')
            self._remotes_cache.pop(name, None)
        else:
            logger.error(f'[ConfigManager] delete_remote 失败: {name}, '
                        f'return_code={result.return_code}, stderr={result.stderr[:300] if result.stderr else "N/A"}')
        return result.success

    def test_remote(self, name: str) -> tuple[bool, str]:
        logger.info(f'[ConfigManager] test_remote: name={name}')
        result = self.rclone.check(name)
        if result.success:
            logger.info(f'[ConfigManager] test_remote 成功: {name}')
            return True, "Connection successful"
        msg = result.stderr or "Connection failed"
        logger.warning(f'[ConfigManager] test_remote 失败: {name}, stderr={msg[:200]}')
        return False, msg

    def get_remote_info(self, name: str) -> Optional[Dict]:
        logger.info(f'[ConfigManager] get_remote_info: name={name}')
        success, info = self.rclone.about(name)
        if success:
            logger.info(f'[ConfigManager] get_remote_info 成功: {name}')
        else:
            logger.warning(f'[ConfigManager] get_remote_info 失败: {name}')
        return info if success else None

