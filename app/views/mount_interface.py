from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel
)

from qfluentwidgets import (
    ScrollArea, FluentIcon as FIF, IconWidget,
    TitleLabel, BodyLabel, StrongBodyLabel, CaptionLabel, PrimaryPushButton,
    PushButton, TransparentPushButton, SimpleCardWidget,
    MessageBox, ComboBox, Dialog, SwitchButton,
    InfoBar, InfoBarPosition, StateToolTip
)

from ..common.signal_bus import signalBus
from ..common.logger import get_logger
from ..core.rclone import RClone
from ..core.config_manager import ConfigManager
from ..core.mount_manager import MountManager
from ..models.mount import Mount, MountStatus

logger = get_logger('mount')


class _DiscoveredUnmountWorker(QThread):
    """在后台线程中执行发现挂载的卸载操作，避免阻塞 GUI 主线程。

    遵循 qthread-lifecycle 规范：
    - finished 信号连接 deleteLater 释放资源
    - 使用 _cancelled 标志支持协作式取消
    """

    finished = Signal(str, bool)  # (discovered_key, success)

    def __init__(self, mount_manager: MountManager, discovered_key: str, parent=None):
        super().__init__(parent)
        self._mount_manager = mount_manager
        self._discovered_key = discovered_key
        self._cancelled = False

    def run(self):
        if self._cancelled:
            self.finished.emit(self._discovered_key, False)
            return
        try:
            success = self._mount_manager.unmount(self._discovered_key)
        except Exception:
            success = False
        if self._cancelled:
            return
        self.finished.emit(self._discovered_key, success)

    def cancel(self):
        self._cancelled = True


class MountCard(SimpleCardWidget):

    mountClicked = Signal(str)
    unmountClicked = Signal(str)
    editClicked = Signal(str)
    deleteClicked = Signal(str)

    def __init__(self, mount: Mount, parent=None):
        super().__init__(parent)
        self.mount = mount
        # 发现挂载用 _discovered_{drive} 作为唯一标识，支持同名异盘
        if mount.source == "discovered":
            self._mount_key = f"_discovered_{mount.drive_letter}"
        else:
            self._mount_key = mount.remote_name
        self.setFixedHeight(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)

        self.iconWidget = IconWidget(FIF.TILES, self)
        self.iconWidget.setFixedSize(40, 40)

        infoLayout = QVBoxLayout()
        infoLayout.setSpacing(2)
        self.nameLabel = StrongBodyLabel(f'{mount.remote_name} → {mount.drive_letter}:', self)

        status_text = {
            MountStatus.UNMOUNTED: '未挂载',
            MountStatus.MOUNTING: '挂载中...',
            MountStatus.MOUNTED: '已挂载',
            MountStatus.ERROR: '错误'
        }
        self.statusLabel = CaptionLabel(status_text.get(mount.status, '未知'), self)
        infoLayout.addWidget(self.nameLabel)
        infoLayout.addWidget(self.statusLabel)

        btnLayout = QHBoxLayout()
        btnLayout.setSpacing(8)

        self.actionBtn = PrimaryPushButton('挂载', self)
        self.actionBtn.setFixedWidth(70)
        self._updateButton()

        self.editBtn = TransparentPushButton('编辑', self)
        self.editBtn.setFixedWidth(60)
        self.editBtn.clicked.connect(lambda: self.editClicked.emit(self._mount_key))

        self.deleteBtn = TransparentPushButton('删除', self)
        self.deleteBtn.setFixedWidth(60)
        self.deleteBtn.clicked.connect(lambda: self.deleteClicked.emit(self._mount_key))

        btnLayout.addWidget(self.actionBtn)
        btnLayout.addWidget(self.editBtn)
        btnLayout.addWidget(self.deleteBtn)

        layout.addWidget(self.iconWidget)
        layout.addSpacing(16)
        layout.addLayout(infoLayout, 1)
        layout.addLayout(btnLayout)

        # 发现挂载的特殊显示：状态标签显示"外部挂载"，隐藏编辑和删除按钮
        if mount.source == "discovered":
            self.statusLabel.setText("外部挂载")
            self.editBtn.hide()
            self.deleteBtn.hide()
            # 发现挂载始终显示卸载按钮
            self._updateButton()

    def _updateButton(self):
        self.actionBtn.blockSignals(True)

        try:
            if hasattr(self, '_current_action_handler'):
                self.actionBtn.clicked.disconnect(self._current_action_handler)
        except (TypeError, RuntimeError):
            pass

        # 发现挂载始终显示"卸载"按钮（基于 mount.status 字段判断，
        # 不使用 is_mounted 实时磁盘检测 —— 参考 mount-button-status-mismatch）
        if self.mount.source == "discovered":
            self.actionBtn.setText('卸载')
            self._current_action_handler = lambda: self.unmountClicked.emit(self._mount_key)
        # 基于 status 判断而非 is_mounted（后者在 Windows 上做实时磁盘检测，
        # 挂载刚完成时盘符可能还未就绪，导致按钮状态不正确）
        elif self.mount.status == MountStatus.MOUNTED:
            self.actionBtn.setText('卸载')
            self._current_action_handler = lambda: self.unmountClicked.emit(self._mount_key)
        else:
            self.actionBtn.setText('挂载')
            self._current_action_handler = lambda: self.mountClicked.emit(self._mount_key)

        self.actionBtn.clicked.connect(self._current_action_handler)
        self.actionBtn.blockSignals(False)

    def updateStatus(self, status: MountStatus):
        self.mount.status = status
        # 发现挂载始终显示"外部挂载"标识
        if self.mount.source == "discovered":
            self.statusLabel.setText("外部挂载")
        else:
            status_text = {
                MountStatus.UNMOUNTED: '未挂载',
                MountStatus.MOUNTING: '挂载中...',
                MountStatus.MOUNTED: '已挂载',
                MountStatus.ERROR: '错误'
            }
            self.statusLabel.setText(status_text.get(status, '未知'))
        self._updateButton()


class AddMountDialog(Dialog):

    def __init__(self, remotes: list, available_drives: list, parent=None, mount: Mount = None):
        self.mount = mount
        self.remotes = remotes
        self.available_drives = available_drives
        title = '编辑挂载' if mount else '添加挂载'
        super().__init__(title, '', parent)

        self.setFixedSize(400, 350)
        self.initUI()

        if mount:
            self.loadMount(mount)

    def initUI(self):
        # 隐藏 Dialog 基类自带的空内容标签
        if hasattr(self, 'contentLabel'):
            self.contentLabel.hide()
            self.contentLabel.setFixedHeight(0)

        # textLayout 默认 stretch=1 会吞掉多余空间，压缩为 0
        self.vBoxLayout.setStretchFactor(self.textLayout, 0)

        # 找到按钮组位置，在其前面插入自定义布局
        button_index = self.vBoxLayout.indexOf(self.buttonGroup)

        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(24, 0, 24, 0)

        layout.addWidget(QLabel('远程存储:'))
        self.remoteCombo = ComboBox(self)
        for remote in self.remotes:
            self.remoteCombo.addItem(remote.name)
        layout.addWidget(self.remoteCombo)

        layout.addWidget(QLabel('盘符:'))
        self.driveCombo = ComboBox(self)
        for drive in self.available_drives:
            self.driveCombo.addItem(f'{drive}:')
        layout.addWidget(self.driveCombo)

        layout.addWidget(QLabel('缓存模式:'))
        self.cacheCombo = ComboBox(self)
        self.cacheCombo.addItems(['off', 'minimal', 'writes', 'full'])
        layout.addWidget(self.cacheCombo)

        autoLayout = QHBoxLayout()
        autoLayout.addWidget(QLabel('开机自动挂载:'))
        self.autoSwitch = SwitchButton(self)
        autoLayout.addStretch()
        autoLayout.addWidget(self.autoSwitch)
        layout.addLayout(autoLayout)

        roLayout = QHBoxLayout()
        roLayout.addWidget(QLabel('只读模式:'))
        self.roSwitch = SwitchButton(self)
        roLayout.addStretch()
        roLayout.addWidget(self.roSwitch)
        layout.addLayout(roLayout)

        self.vBoxLayout.insertLayout(button_index, layout)

        # 在自定义内容和按钮栏之间插入弹性空间
        new_button_index = self.vBoxLayout.indexOf(self.buttonGroup)
        self.vBoxLayout.insertStretch(new_button_index, 1)

        # 按钮文本汉化
        self.yesButton.setText('确认')
        self.cancelButton.setText('取消')

    def loadMount(self, mount: Mount):
        idx = self.remoteCombo.findText(mount.remote_name)
        if idx >= 0:
            self.remoteCombo.setCurrentIndex(idx)
        self.remoteCombo.setEnabled(False)

        if mount.drive_letter not in self.available_drives:
            self.driveCombo.insertItem(0, f'{mount.drive_letter}:')
        idx = self.driveCombo.findText(f'{mount.drive_letter}:')
        if idx >= 0:
            self.driveCombo.setCurrentIndex(idx)

        idx = self.cacheCombo.findText(mount.cache_mode)
        if idx >= 0:
            self.cacheCombo.setCurrentIndex(idx)

        self.autoSwitch.setChecked(mount.auto_mount)
        self.roSwitch.setChecked(mount.read_only)

    def getData(self) -> dict:
        return {
            'remote_name': self.remoteCombo.currentText(),
            'drive_letter': self.driveCombo.currentText().rstrip(':'),
            'cache_mode': self.cacheCombo.currentText(),
            'auto_mount': self.autoSwitch.isChecked(),
            'read_only': self.roSwitch.isChecked()
        }


class MountInterface(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('mountInterface')
        self.setWidgetResizable(True)

        self.rclone = RClone()
        self.configManager = ConfigManager(self.rclone)
        self.mountManager = MountManager(self.rclone)
        self.mountManager.load_mounts()

        self.mountCards: dict = {}
        self._unmount_worker = None

        self.initUI()
        self.connectSignals()
        self.loadMounts()

    def initUI(self):
        self.scrollWidget = QWidget()
        self.setWidget(self.scrollWidget)
        self.enableTransparentBackground()

        self.mainLayout = QVBoxLayout(self.scrollWidget)
        self.mainLayout.setContentsMargins(36, 20, 36, 20)
        self.mainLayout.setSpacing(16)

        headerLayout = QHBoxLayout()
        self.titleLabel = TitleLabel('挂载管理', self)
        self.addBtn = PrimaryPushButton(FIF.ADD, '添加', self)
        self.addBtn.clicked.connect(self.showAddDialog)
        self.mountAllBtn = PushButton(FIF.PLAY, '全部挂载', self)
        self.mountAllBtn.clicked.connect(self.mountAll)
        self.unmountAllBtn = PushButton(FIF.PAUSE, '全部卸载', self)
        self.unmountAllBtn.clicked.connect(self.unmountAll)

        headerLayout.addWidget(self.titleLabel)
        headerLayout.addStretch()
        headerLayout.addWidget(self.mountAllBtn)
        headerLayout.addWidget(self.unmountAllBtn)
        headerLayout.addWidget(self.addBtn)

        self.mainLayout.addLayout(headerLayout)

        self.listWidget = QWidget()
        self.listLayout = QVBoxLayout(self.listWidget)
        self.listLayout.setContentsMargins(0, 0, 0, 0)
        self.listLayout.setSpacing(8)

        self.mainLayout.addWidget(self.listWidget)
        self.mainLayout.addStretch()

    def connectSignals(self):
        self.mountManager.mountStatusChanged.connect(self.onMountStatusChanged)
        self.mountManager.mountError.connect(self.onMountError)

    def loadMounts(self):
        # 刷新挂载状态，确保发现挂载已加载
        self.mountManager.refresh_mount_status()

        while self.listLayout.count():
            item = self.listLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.mountCards.clear()

        if not self.mountManager.mounts:
            emptyLabel = CaptionLabel('暂无挂载配置，点击"添加"创建', self)
            emptyLabel.setAlignment(Qt.AlignCenter)
            self.listLayout.addWidget(emptyLabel)
            return

        for name, mount in self.mountManager.mounts.items():
            card = MountCard(mount, self)
            card.mountClicked.connect(self.doMount)
            card.unmountClicked.connect(self.doUnmount)
            card.editClicked.connect(self.showEditDialog)
            card.deleteClicked.connect(self.deleteMount)
            self.listLayout.addWidget(card)
            # 发现挂载用 _discovered_{drive} key，配置挂载用 remote_name
            self.mountCards[card._mount_key] = card

    def showAddDialog(self):
        self.configManager.refresh()
        remotes = self.configManager.list_remotes()

        if not remotes:
            logger.warning('用户尝试添加挂载但无远程存储配置')
            InfoBar.warning('提示', '请先添加远程存储',
                           parent=self, position=InfoBarPosition.TOP)
            return

        available_drives = self.mountManager.get_available_drives()
        if not available_drives:
            logger.error('没有可用的盘符')
            InfoBar.error('错误', '没有可用的盘符',
                         parent=self, position=InfoBarPosition.TOP)
            return

        dialog = AddMountDialog(remotes, available_drives, self)
        if dialog.exec():
            data = dialog.getData()
            logger.info(f'用户添加挂载配置: {data["remote_name"]} → {data["drive_letter"]}:')
            self.mountManager.add_mount(**data)
            self.loadMounts()
            InfoBar.success('成功', f'已添加挂载配置',
                           parent=self, position=InfoBarPosition.TOP)

    def showEditDialog(self, name: str):
        logger.info(f'用户打开编辑挂载对话框: {name}')
        mount = self.mountManager.mounts.get(name)
        if not mount:
            logger.warning(f'未找到挂载配置: {name}')
            return

        self.configManager.refresh()
        remotes = self.configManager.list_remotes()
        available_drives = self.mountManager.get_available_drives()

        dialog = AddMountDialog(remotes, available_drives, self, mount)
        if dialog.exec():
            data = dialog.getData()
            logger.info(f'用户更新挂载配置: {name} → {data["drive_letter"]}:')
            mount.drive_letter = data['drive_letter']
            mount.cache_mode = data['cache_mode']
            mount.auto_mount = data['auto_mount']
            mount.read_only = data['read_only']
            self.mountManager.save_mounts()
            self.loadMounts()

    def deleteMount(self, name: str):
        logger.info(f'用户请求删除挂载配置: {name}')
        box = MessageBox('确认删除', f'确定要删除挂载配置 "{name}" 吗？', self.window())
        if box.exec():
            logger.info(f'用户确认删除挂载配置: {name}')
            self.mountManager.remove_mount(name)
            logger.info(f'挂载配置已删除: {name}')
            self.loadMounts()
        else:
            logger.info(f'用户取消删除挂载配置: {name}')

    def doMount(self, name: str):
        logger.info(f'用户请求挂载: {name}')
        self.mountManager.mount(name)

    def doUnmount(self, name: str):
        logger.info(f'用户请求卸载: {name}')

        mount = self.mountManager.mounts.get(name)

        if mount and mount.source == "discovered":
            discovered_key = name  # 现在 name 直接就是 _discovered_{drive} key

            # 取消已有的卸载 worker（qthread-lifecycle 规范）
            if self._unmount_worker is not None:
                if self._unmount_worker.isRunning():
                    self._unmount_worker.cancel()
                    self._unmount_worker.wait(1000)
                    self._unmount_worker.deleteLater()

            # 禁用所有卸载按钮和"全部卸载"按钮
            self._setUnmountButtonsEnabled(False)

            # 在后台线程中执行卸载，避免阻塞 GUI 主线程
            self._unmount_worker = _DiscoveredUnmountWorker(
                self.mountManager, discovered_key
            )
            self._unmount_worker.finished.connect(self._onDiscoveredUnmountFinished)
            self._unmount_worker.finished.connect(self._unmount_worker.deleteLater)
            self._unmount_worker.start()

            InfoBar.info(
                '卸载中',
                f'正在卸载外部挂载 {mount.drive_letter}: ...',
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000
            )
        else:
            self.mountManager.unmount(name)


    def _onDiscoveredUnmountFinished(self, discovered_key: str, success: bool):
        """发现挂载异步卸载完成的回调槽。"""
        if success:
            with self.mountManager._lock:
                self.mountManager.mounts.pop(discovered_key, None)
            self.loadMounts()
        else:
            # 从 discovered_key 提取盘符用于错误提示
            drive = discovered_key.replace("_discovered_", "")
            InfoBar.error(
                '卸载失败',
                f'无法卸载外部挂载 {drive}:',
                parent=self,
                position=InfoBarPosition.TOP
            )
            # 恢复按钮状态
            self._setUnmountButtonsEnabled(True)
        self._unmount_worker = None

    def _setUnmountButtonsEnabled(self, enabled: bool):
        """启用或禁用所有卸载相关按钮。"""
        self.unmountAllBtn.setEnabled(enabled)
        for card in self.mountCards.values():
            if card.actionBtn.text() == '卸载':
                card.actionBtn.setEnabled(enabled)

    def mountAll(self):
        logger.info('用户请求全部挂载')
        for mount in self.mountManager.mounts.values():
            if not mount.is_mounted:
                self.mountManager.mount(mount.remote_name)

    def unmountAll(self):
        logger.info('用户请求全部卸载')
        self.mountManager.unmount_all()
        self.loadMounts()

    def onMountStatusChanged(self, name: str, status: MountStatus):
        logger.info(f'挂载状态变更: {name} → {status.name}')
        if name in self.mountCards:
            self.mountCards[name].updateStatus(status)
        elif name not in self.mountManager.mounts:
            self.loadMounts()

    def onMountError(self, name: str, error: str):
        logger.error(f'挂载失败: {name}, error={error}')
        InfoBar.error('挂载失败', f'{name}: {error}',
                     parent=self, position=InfoBarPosition.TOP)
