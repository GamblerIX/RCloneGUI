import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
)

from qfluentwidgets import (
    ScrollArea, FluentIcon as FIF, SettingCardGroup,
    SwitchSettingCard, ComboBoxSettingCard, PushSettingCard,
    PrimaryPushSettingCard, HyperlinkCard, OptionsSettingCard,
    TitleLabel, setTheme, Theme, isDarkTheme, qconfig
)

from ..common.config import cfg, get_system_theme, CacheDirMode, get_cache_dir, DEFAULT_CACHE_DIR
from ..common.signal_bus import signalBus
from ..common.auto_start import set_auto_start, is_auto_start_enabled
from ..common.logger import get_logger
from ..core.rclone import RClone
from qfluentwidgets import InfoBar, InfoBarPosition

logger = get_logger('settings')


class SettingsInterface(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('settingsInterface')
        self.setWidgetResizable(True)

        self.rclone = RClone()
        self.initUI()
        self.syncAutoStartState()

    def initUI(self):
        self.scrollWidget = QWidget()
        self.setWidget(self.scrollWidget)
        self.enableTransparentBackground()

        self.mainLayout = QVBoxLayout(self.scrollWidget)
        self.mainLayout.setContentsMargins(36, 20, 36, 20)
        self.mainLayout.setSpacing(20)

        self.titleLabel = TitleLabel('设置', self)
        self.mainLayout.addWidget(self.titleLabel)

        self.rcloneGroup = SettingCardGroup('RClone 设置', self)

        self.rcloneVersionCard = PushSettingCard(
            '查看版本',
            FIF.INFO,
            'RClone 版本',
            self.rclone.version(),
            self.rcloneGroup
        )
        self.rcloneVersionCard.clicked.connect(self.showRcloneVersion)

        self.rclonePathCard = PushSettingCard(
            '选择',
            FIF.FOLDER,
            'RClone 路径',
            cfg.rclonePath.value,
            self.rcloneGroup
        )
        self.rclonePathCard.clicked.connect(self.selectRclonePath)

        self.rcloneGroup.addSettingCard(self.rcloneVersionCard)
        self.rcloneGroup.addSettingCard(self.rclonePathCard)

        self.appGroup = SettingCardGroup('应用设置', self)

        self.themeCard = OptionsSettingCard(
            cfg.themeMode,
            FIF.BRUSH,
            '主题',
            '选择应用主题',
            texts=['浅色', '深色', '跟随系统'],
            parent=self.appGroup
        )
        self.themeCard.optionChanged.connect(self.onThemeChanged)

        self.autoStartCard = SwitchSettingCard(
            FIF.POWER_BUTTON,
            '开机自启',
            '开机时自动启动应用',
            cfg.autoStart,
            self.appGroup
        )
        self.autoStartCard.checkedChanged.connect(self.onAutoStartChanged)

        self.minimizeToTrayCard = SwitchSettingCard(
            FIF.MINIMIZE,
            '最小化到托盘',
            '点击最小化时隐藏到系统托盘',
            cfg.minimizeToTray,
            self.appGroup
        )
        self.minimizeToTrayCard.checkedChanged.connect(
            lambda checked: logger.info(f'用户更改最小化到托盘设置: {checked}')
        )

        self.closeToTrayCard = SwitchSettingCard(
            FIF.CLOSE,
            '关闭到托盘',
            '点击关闭按钮时隐藏到系统托盘而非退出',
            cfg.closeToTray,
            self.appGroup
        )
        self.closeToTrayCard.checkedChanged.connect(
            lambda checked: logger.info(f'用户更改关闭到托盘设置: {checked}')
        )

        self.appGroup.addSettingCard(self.themeCard)
        self.appGroup.addSettingCard(self.autoStartCard)
        self.appGroup.addSettingCard(self.minimizeToTrayCard)
        self.appGroup.addSettingCard(self.closeToTrayCard)

        self.mountGroup = SettingCardGroup('挂载设置', self)

        self.autoMountCard = SwitchSettingCard(
            FIF.PLAY,
            '自动挂载',
            '启动时自动挂载所有配置为自动挂载的存储',
            cfg.autoMount,
            self.mountGroup
        )
        self.autoMountCard.checkedChanged.connect(
            lambda checked: logger.info(f'用户更改自动挂载设置: {checked}')
        )

        self.cacheDirModeCard = ComboBoxSettingCard(
            cfg.cacheDirMode,
            FIF.FOLDER,
            'VFS 缓存目录',
            self._get_cache_dir_description(),
            texts=['默认 (cache 目录)', '系统临时目录', '自定义目录'],
            parent=self.mountGroup
        )
        self.cacheDirModeCard.comboBox.currentIndexChanged.connect(self.onCacheDirModeChanged)

        self.cacheDirCustomCard = PushSettingCard(
            '选择',
            FIF.EDIT,
            '自定义缓存路径',
            cfg.cacheDirCustomPath.value or '未设置',
            self.mountGroup
        )
        self.cacheDirCustomCard.clicked.connect(self.selectCacheDir)
        self.cacheDirCustomCard.setVisible(cfg.cacheDirMode.value == CacheDirMode.CUSTOM)

        self.mountGroup.addSettingCard(self.autoMountCard)
        self.mountGroup.addSettingCard(self.cacheDirModeCard)
        self.mountGroup.addSettingCard(self.cacheDirCustomCard)

        self.aboutGroup = SettingCardGroup('关于', self)

        self.aboutCard = PrimaryPushSettingCard(
            '查看项目',
            FIF.GITHUB,
            'RClone GUI',
            '基于 PySide6 + QFluentWidgets 的 RClone 图形界面',
            self.aboutGroup
        )
        self.aboutCard.clicked.connect(self.openProjectUrl)

        self.aboutGroup.addSettingCard(self.aboutCard)

        self.mainLayout.addWidget(self.rcloneGroup)
        self.mainLayout.addWidget(self.appGroup)
        self.mainLayout.addWidget(self.mountGroup)
        self.mainLayout.addWidget(self.aboutGroup)
        self.mainLayout.addStretch()

    def selectRclonePath(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 RClone 可执行文件',
            filter='Executable (*.exe)' if __import__('os').name == 'nt' else 'All Files (*)'
        )
        if path:
            logger.info(f'用户更改 RClone 路径: {path}')
            cfg.rclonePath.value = path
            self.rclonePathCard.setContent(path)
            self.rclone.rclone_path = path
            self.rcloneVersionCard.setContent(self.rclone.version())
            logger.info(f'RClone 版本已更新: {self.rclone.version()}')

    def selectCacheDir(self):
        path = QFileDialog.getExistingDirectory(self, '选择缓存目录')
        if path:
            logger.info(f'用户更改自定义缓存目录: {path}')
            cfg.cacheDirCustomPath.value = path
            self.cacheDirCustomCard.setContent(path)
            self.cacheDirModeCard.setContent(self._get_cache_dir_description())

    def onCacheDirModeChanged(self, index):
        modes = [CacheDirMode.DEFAULT, CacheDirMode.SYSTEM_TEMP, CacheDirMode.CUSTOM]
        mode = modes[index]
        logger.info(f'用户更改缓存目录模式: {mode.value}')
        self.cacheDirCustomCard.setVisible(mode == CacheDirMode.CUSTOM)
        self.cacheDirModeCard.setContent(self._get_cache_dir_description())

    def _get_cache_dir_description(self) -> str:
        mode = cfg.cacheDirMode.value
        if mode == CacheDirMode.DEFAULT:
            return str(DEFAULT_CACHE_DIR)
        elif mode == CacheDirMode.SYSTEM_TEMP:
            import tempfile
            return tempfile.gettempdir()
        elif mode == CacheDirMode.CUSTOM:
            return cfg.cacheDirCustomPath.value or '未设置，请选择目录'
        return ''

    def onThemeChanged(self, configItem):
        theme = configItem.value
        theme_name = '浅色' if theme == Theme.LIGHT else '深色' if theme == Theme.DARK else '跟随系统'
        logger.info(f'用户更改主题: {theme_name}')
        if theme == Theme.AUTO:
            system_theme = get_system_theme()
            setTheme(system_theme, save=False)
            qconfig.themeMode.value = Theme.AUTO
            actual_theme_name = '浅色' if system_theme == Theme.LIGHT else '深色'
            logger.info(f'自动检测系统主题: {actual_theme_name}')
        else:
            setTheme(theme)
        signalBus.themeChanged.emit()

    def syncAutoStartState(self):
        try:
            registry_enabled = is_auto_start_enabled()
            config_enabled = cfg.autoStart.value

            if registry_enabled != config_enabled:
                logger.info(f'同步开机自启状态: 注册表={registry_enabled}, 配置={config_enabled}')
                cfg.autoStart.value = registry_enabled
                self.autoStartCard.setChecked(registry_enabled)
        except Exception as e:
            logger.warning(f'同步开机自启状态失败: {e}')

    def onAutoStartChanged(self, enabled: bool):
        logger.info(f'用户更改开机自启设置: {enabled}')
        success = set_auto_start(enabled)
        if success:
            status = "已开启" if enabled else "已关闭"
            logger.info(f'开机自启设置成功: {status}')
            InfoBar.success(
                '开机自启',
                f'开机自启功能{status}',
                parent=self,
                position=InfoBarPosition.TOP
            )
        else:
            logger.error('开机自启设置失败')
            self.autoStartCard.setChecked(not enabled)
            InfoBar.error(
                '错误',
                '设置开机自启失败，请以管理员身份运行或检查权限',
                parent=self,
                position=InfoBarPosition.TOP
            )

    def showRcloneVersion(self):
        from PySide6.QtWidgets import QMessageBox
        version = self.rclone.version()
        logger.info(f'用户查看 RClone 版本: {version}')
        QMessageBox.information(
            self,
            'RClone 版本信息',
            f'当前 RClone 版本:\n\n{version}\n\n路径: {cfg.rclonePath.value}'
        )

    def openProjectUrl(self):
        import webbrowser
        url = 'https://github.com/GamblerIX/RCloneGUI'
        logger.info(f'用户打开项目页面: {url}')
        webbrowser.open(url)
        InfoBar.success(
            '项目页面',
            '正在打开浏览器...',
            parent=self,
            position=InfoBarPosition.TOP
        )
