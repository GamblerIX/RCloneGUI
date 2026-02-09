import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from qfluentwidgets import (
    NavigationInterface, NavigationItemPosition, NavigationWidget,
    FluentWindow, SplashScreen,
    FluentIcon as FIF, NavigationAvatarWidget, qrouter
)

from .home_interface import HomeInterface
from .remote_interface import RemoteInterface
from .mount_interface import MountInterface
from .browser_interface import BrowserInterface
from .sync_interface import SyncInterface
from .settings_interface import SettingsInterface
from ..common.config import cfg
from ..common.signal_bus import signalBus


class MainWindow(FluentWindow):

    def __init__(self):
        super().__init__()
        self.initWindow()
        self.initNavigation()
        self.connectSignals()

    def initWindow(self):
        self.setWindowTitle('RClone GUI')
        self.setMinimumSize(960, 640)
        self.resize(1100, 750)

        screen = QApplication.primaryScreen()
        if screen is None:
            screen = QApplication.screens()[0] if QApplication.screens() else None
        if screen:
            desktop = screen.availableGeometry()
            w, h = desktop.width(), desktop.height()
            self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)


        self.navigationInterface.setExpandWidth(150)

    def initNavigation(self):
        self.homeInterface = HomeInterface(self)
        self.remoteInterface = RemoteInterface(self)
        self.mountInterface = MountInterface(self)
        self.browserInterface = BrowserInterface(self)
        self.syncInterface = SyncInterface(self)
        self.settingsInterface = SettingsInterface(self)

        self.addSubInterface(self.homeInterface, FIF.HOME, '首页')
        self.addSubInterface(self.remoteInterface, FIF.CLOUD, '远程存储')
        self.addSubInterface(self.mountInterface, FIF.TILES, '挂载管理')
        self.addSubInterface(self.browserInterface, FIF.FOLDER, '文件浏览')
        self.addSubInterface(self.syncInterface, FIF.SYNC, '同步任务')

        self.addSubInterface(
            self.settingsInterface, FIF.SETTING, '设置',
            position=NavigationItemPosition.BOTTOM
        )

        self.navigationInterface.setCurrentItem(self.homeInterface.objectName())

    def connectSignals(self):
        signalBus.switchToInterface.connect(self.switchToInterface)
        signalBus.showMainWindow.connect(self.showNormal)

    def switchToInterface(self, interface_name: str):
        interface_map = {
            'home': self.homeInterface,
            'remote': self.remoteInterface,
            'mount': self.mountInterface,
            'browser': self.browserInterface,
            'sync': self.syncInterface,
            'settings': self.settingsInterface,
        }
        if interface_name in interface_map:
            self.switchTo(interface_map[interface_name])

    def closeEvent(self, event):
        if cfg.closeToTray.value:
            event.ignore()
            self.hide()
            signalBus.hideMainWindow.emit()
        else:
            event.accept()
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app and hasattr(app, '_tray'):
                app._tray.exitApp()
