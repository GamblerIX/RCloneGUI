import sys
import os
import signal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtNetwork import QLocalSocket, QLocalServer

from qfluentwidgets import FluentIcon as FIF, setTheme, Theme, qconfig

from app.views.main_window import MainWindow
from app.common.config import cfg, get_system_theme
from app.common.signal_bus import signalBus
from app.common.logger import app_logger
from app.core.bootstrap import bootstrap, is_rclone_available
from app.core.rclone import RClone
from app.core.mount_manager import MountManager
from app.core.sync_manager import SyncManager


g_app = None
g_window = None
g_tray = None
g_sync_manager = None


def apply_theme_with_auto_detection(theme: Theme):
    if theme == Theme.AUTO:
        system_theme = get_system_theme()
        setTheme(system_theme, save=False)
        qconfig.themeMode.value = Theme.AUTO
        app_logger.info(f'自动检测系统主题: {"浅色" if system_theme == Theme.LIGHT else "深色"}')
    else:
        setTheme(theme)


APP_ID = "RCloneGUI-SingleInstance-Lock"


class SystemTray(QSystemTrayIcon):

    def __init__(self, window: MainWindow, parent=None):
        super().__init__(parent)
        self.window = window
        self.mountManager = MountManager()
        self.mountManager.load_mounts()

        self.setIcon(FIF.CLOUD.icon())
        self.setToolTip('RClone GUI')

        self.initMenu()
        self.activated.connect(self.onActivated)
        app_logger.info('系统托盘已初始化')

    def initMenu(self):
        self.menu = QMenu()

        self.showAction = QAction('显示主窗口', self)
        self.showAction.triggered.connect(self.showWindow)
        self.menu.addAction(self.showAction)

        self.menu.addSeparator()

        self.mountAllAction = QAction('全部挂载', self)
        self.mountAllAction.triggered.connect(self.mountAll)
        self.menu.addAction(self.mountAllAction)

        self.unmountAllAction = QAction('全部卸载', self)
        self.unmountAllAction.triggered.connect(self.unmountAll)
        self.menu.addAction(self.unmountAllAction)

        self.menu.addSeparator()

        self.exitAction = QAction('退出', self)
        self.exitAction.triggered.connect(self.exitApp)
        self.menu.addAction(self.exitAction)

        self.setContextMenu(self.menu)

    def onActivated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showWindow()

    def showWindow(self):
        self.window.showNormal()
        self.window.activateWindow()
        signalBus.showMainWindow.emit()

    def mountAll(self):
        app_logger.info('托盘: 执行全部挂载')
        self.mountManager.auto_mount_all()
        self.showMessage('RClone GUI', '正在挂载所有存储...')

    def unmountAll(self):
        app_logger.info('托盘: 执行全部卸载')
        self.mountManager.unmount_all()
        self.showMessage('RClone GUI', '已卸载所有存储')

    def exitApp(self):
        app_logger.info('=== RClone GUI 关闭 ===')
        self._cleanup_and_exit()

    def _cleanup_and_exit(self):
        global g_app, g_window

        try:
            if g_window and hasattr(g_window, 'syncInterface') and g_window.syncInterface:
                if hasattr(g_window.syncInterface, 'syncManager') and g_window.syncInterface.syncManager:
                    g_window.syncInterface.syncManager.shutdown()
                    app_logger.info('同步管理器已关闭')
        except Exception as e:
            app_logger.error(f'关闭同步管理器失败: {e}')

        try:
            self.mountManager.unmount_all()
        except Exception as e:
            app_logger.error(f'卸载挂载失败: {e}')

        self._kill_rclone_processes()

        self.hide()

        if g_app:
            g_app.processEvents()

        if g_app:
            g_app.quit()

        os._exit(0)

    def _kill_rclone_processes(self):
        try:
            import subprocess
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq rclone*.exe', '/NH'],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if 'rclone' in result.stdout.lower():
                subprocess.run(
                    ['taskkill', '/F', '/T', '/IM', 'rclone.exe'],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
                )
                app_logger.info('已终止所有 rclone 进程（包括子进程）')
        except Exception as e:
            app_logger.debug(f'终止 rclone 进程时出错: {e}')


def check_single_instance() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(APP_ID)
    if socket.waitForConnected(500):
        socket.close()
        return False
    return True


def create_local_server() -> QLocalServer | None:
    server = QLocalServer()
    QLocalServer.removeServer(APP_ID)
    if server.listen(APP_ID):
        return server
    return None


def main():
    global g_app, g_window, g_tray, g_sync_manager

    try:
        success, error_msg = bootstrap()
        if not success:
            print(f'启动检查失败: {error_msg}', file=sys.stderr)
            try:
                app = QApplication(sys.argv)
                from PySide6.QtWidgets import QMessageBox
                msg_box = QMessageBox()
                msg_box.setWindowTitle('RClone GUI - 启动检查失败')
                msg_box.setText(error_msg)
                msg_box.setIcon(QMessageBox.Critical)
                msg_box.exec()
                app.quit()
                del app
            except Exception:
                pass
            sys.exit(1)

        if not check_single_instance():
            print('RClone GUI 已经在运行中', file=sys.stderr)
            app = None
            try:
                app = QApplication.instance()
                if app is None:
                    app = QApplication(sys.argv)
                from PySide6.QtWidgets import QMessageBox
                msg_box = QMessageBox()
                msg_box.setWindowTitle('RClone GUI')
                msg_box.setText('RClone GUI 已经在运行中')
                msg_box.setIcon(QMessageBox.Information)
                msg_box.exec()
            except Exception:
                pass
            finally:
                if app is not None:
                    app.quit()
                    del app
            sys.exit(0)

        app_logger.info('=== RClone GUI 启动 ===')

        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        g_app = app

        local_server = create_local_server()
        if local_server:
            app._local_server = local_server
        app.setApplicationName('RClone GUI')
        app.setOrganizationName('RCloneGUI')

        theme = cfg.themeMode.value
        apply_theme_with_auto_detection(theme)

        window = MainWindow()
        g_window = window

        if QSystemTrayIcon.isSystemTrayAvailable():
            tray = SystemTray(window)
            g_tray = tray
            tray.show()
            app._tray = tray
        else:
            app_logger.warning('系统托盘不可用')

        if cfg.autoMount.value and hasattr(app, '_tray') and is_rclone_available():
            try:
                app._tray.mountManager.auto_mount_all()
            except Exception as e:
                app_logger.error(f'自动挂载失败: {e}')
                from PySide6.QtWidgets import QMessageBox
                msg_box = QMessageBox()
                msg_box.setWindowTitle('自动挂载警告')
                msg_box.setText(f'自动挂载初始化失败: {str(e)}')
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.exec()

        window.show()

        # rclone 缺失时显示下载遮罩，阻止用户操作
        if not is_rclone_available():
            app_logger.info('rclone 未找到，显示下载遮罩')
            from app.views.download_overlay import DownloadOverlay
            from PySide6.QtWidgets import QMessageBox

            overlay = DownloadOverlay(window)
            overlay.setGeometry(window.centralWidget().rect() if window.centralWidget() else window.rect())
            overlay.raise_()
            overlay.show()

            def _on_download_finished(success, error_msg):
                if success:
                    app_logger.info('rclone 下载完成，应用就绪')
                    # 刷新远程存储列表
                    if hasattr(window, 'remoteInterface'):
                        window.remoteInterface.loadRemotes()
                    # 执行自动挂载（如果启用）
                    if cfg.autoMount.value and hasattr(app, '_tray'):
                        try:
                            app._tray.mountManager.auto_mount_all()
                        except Exception as e:
                            app_logger.error(f'自动挂载失败: {e}')
                else:
                    app_logger.error(f'rclone 下载失败: {error_msg}')
                    msg_box = QMessageBox()
                    msg_box.setWindowTitle('RClone GUI - 下载失败')
                    msg_box.setText(f'自动下载 rclone 失败:\n{error_msg}\n\n'
                                   f'请手动下载 rclone 并放置到 environments 目录。')
                    msg_box.setIcon(QMessageBox.Critical)
                    msg_box.exec()

            overlay.downloadFinished.connect(_on_download_finished)
            overlay.startDownload()

            # 让遮罩跟随窗口大小变化
            _orig_resize = window.resizeEvent
            def _patched_resize(event):
                if overlay and not overlay.isHidden():
                    overlay.setGeometry(window.centralWidget().rect() if window.centralWidget() else window.rect())
                _orig_resize(event)
            window.resizeEvent = _patched_resize

        def signal_handler(sig, frame):
            app_logger.info('接收到信号，正在退出...')
            if hasattr(app, '_tray'):
                app._tray.exitApp()
            else:
                app.quit()
                os._exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        sys.exit(app.exec())

    except Exception as e:
        app_logger.critical(f'应用启动失败: {e}', exc_info=True)

        try:
            from PySide6.QtWidgets import QMessageBox
            error_app = QApplication.instance()
            if error_app is None:
                error_app = QApplication(sys.argv)
            msg_box = QMessageBox()
            msg_box.setWindowTitle('启动错误')
            msg_box.setText(f'应用启动失败:\n{str(e)}')
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.exec()
        except Exception as dialog_error:
            print(f'应用启动失败: {e}', file=sys.stderr)
            print(f'无法显示错误对话框: {dialog_error}', file=sys.stderr)

        sys.exit(1)


if __name__ == '__main__':
    main()
