from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from qfluentwidgets import (
    ScrollArea, FluentIcon as FIF, CardWidget, IconWidget,
    TitleLabel, BodyLabel, StrongBodyLabel, SubtitleLabel,
    CaptionLabel, PrimaryPushButton,
    TransparentPushButton, SimpleCardWidget,
    InfoBar, InfoBarPosition
)

from ..common.signal_bus import signalBus
from ..common.logger import get_logger
from ..core.rclone import RClone
from ..core.config_manager import ConfigManager
from ..core.mount_manager import MountManager

logger = get_logger('home')


class StatCard(SimpleCardWidget):

    def __init__(self, icon: FIF, title: str, value: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(40, 40)

        textLayout = QVBoxLayout()
        textLayout.setSpacing(4)
        self.titleLabel = CaptionLabel(title, self)
        self.valueLabel = TitleLabel(value, self)
        textLayout.addWidget(self.titleLabel)
        textLayout.addWidget(self.valueLabel)

        layout.addWidget(self.iconWidget)
        layout.addSpacing(16)
        layout.addLayout(textLayout)
        layout.addStretch()

    def setValue(self, value: str):
        self.valueLabel.setText(value)


class QuickActionCard(SimpleCardWidget):

    def __init__(self, icon: FIF, title: str, description: str, button_text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(48, 48)

        textLayout = QVBoxLayout()
        textLayout.setSpacing(4)
        self.titleLabel = StrongBodyLabel(title, self)
        self.descLabel = CaptionLabel(description, self)
        textLayout.addWidget(self.titleLabel)
        textLayout.addWidget(self.descLabel)
        textLayout.addStretch()

        self.button = PrimaryPushButton(button_text, self)
        self.button.setFixedWidth(100)

        layout.addWidget(self.iconWidget)
        layout.addSpacing(16)
        layout.addLayout(textLayout, 1)
        layout.addWidget(self.button, 0, Qt.AlignVCenter)


class HomeInterface(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('homeInterface')
        self.setWidgetResizable(True)

        self.rclone = RClone()
        self.configManager = ConfigManager(self.rclone)
        self.mountManager = MountManager(self.rclone)

        self.initUI()
        self.loadData()

    def initUI(self):
        self.scrollWidget = QWidget()
        self.setWidget(self.scrollWidget)
        self.enableTransparentBackground()

        self.mainLayout = QVBoxLayout(self.scrollWidget)
        self.mainLayout.setContentsMargins(36, 20, 36, 20)
        self.mainLayout.setSpacing(20)

        self.titleLabel = TitleLabel('仪表盘', self)
        self.mainLayout.addWidget(self.titleLabel)

        self.versionLabel = CaptionLabel(f'RClone: {self.rclone.version()}', self)
        self.mainLayout.addWidget(self.versionLabel)

        statsLayout = QHBoxLayout()
        statsLayout.setSpacing(16)

        self.remoteCard = StatCard(FIF.CLOUD, '远程存储', '0', self)
        self.mountCard = StatCard(FIF.TILES, '已挂载', '0', self)
        self.syncCard = StatCard(FIF.SYNC, '同步任务', '0', self)

        statsLayout.addWidget(self.remoteCard)
        statsLayout.addWidget(self.mountCard)
        statsLayout.addWidget(self.syncCard)

        self.mainLayout.addLayout(statsLayout)

        actionLabel = SubtitleLabel('快捷操作', self)
        self.mainLayout.addSpacing(10)
        self.mainLayout.addWidget(actionLabel)

        self.addRemoteCard = QuickActionCard(
            FIF.ADD, '添加远程存储',
            '配置新的云存储或网络存储连接',
            '添加', self
        )
        self.addRemoteCard.button.clicked.connect(
            lambda: signalBus.switchToInterface.emit('remote')
        )

        self.mountAllCard = QuickActionCard(
            FIF.PLAY, '一键挂载',
            '挂载所有配置为自动挂载的存储',
            '挂载', self
        )
        self.mountAllCard.button.clicked.connect(self.mountAll)

        self.mainLayout.addWidget(self.addRemoteCard)
        self.mainLayout.addWidget(self.mountAllCard)
        self.mainLayout.addStretch()

    def loadData(self):
        try:
            remotes = self.configManager.list_remotes()
            self.remoteCard.setValue(str(len(remotes)))

            self.mountManager.load_mounts()
            mounted = sum(1 for m in self.mountManager.mounts.values() if m.is_mounted)
            self.mountCard.setValue(str(mounted))
        except Exception as e:
            logger.warning(f"加载仪表盘数据失败: {e}")
            InfoBar.warning(
                '数据加载失败',
                '无法加载远程存储信息，请检查配置',
                parent=self,
                position=InfoBarPosition.TOP
            )

    def mountAll(self):
        self.mountManager.auto_mount_all()
        self.loadData()
