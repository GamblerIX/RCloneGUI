"""
rclone 下载遮罩层。

在主窗口上显示全屏半透明遮罩，告知用户正在自动下载 rclone，
同时禁止所有用户操作。下载完成后自动移除。
"""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtGui import QPainter, QColor

from app.core.bootstrap import ensure_rclone, BootstrapError, get_rclone_path
from app.common.logger import app_logger


class RCloneDownloadWorker(QThread):
    """后台线程执行 rclone 下载。"""
    finished = Signal(bool, str)  # (success, error_message)

    def __init__(self, rclone_path, parent=None):
        super().__init__(parent)
        self.rclone_path = rclone_path

    def run(self):
        try:
            ensure_rclone(self.rclone_path)
            self.finished.emit(True, "")
        except BootstrapError as e:
            self.finished.emit(False, str(e))
        except Exception as e:
            self.finished.emit(False, f"下载失败: {e}")


class DownloadOverlay(QWidget):
    """全屏半透明遮罩，显示下载状态并阻止用户交互。"""
    downloadFinished = Signal(bool, str)  # (success, error_message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.WindowType.Widget)

        # 覆盖整个父窗口
        if parent:
            self.setGeometry(parent.rect())

        self._worker = None
        self._initUI()

    def _initUI(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.titleLabel = QLabel("正在自动下载 RClone...")
        self.titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.titleLabel.setStyleSheet(
            "color: white; font-size: 22px; font-weight: bold; background: transparent;"
        )

        self.statusLabel = QLabel("首次运行需要下载 RClone 核心组件，请稍候")
        self.statusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.statusLabel.setStyleSheet(
            "color: rgba(255,255,255,180); font-size: 14px; background: transparent;"
        )

        self.hintLabel = QLabel("下载完成后将自动进入应用")
        self.hintLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hintLabel.setStyleSheet(
            "color: rgba(255,255,255,120); font-size: 12px; background: transparent;"
        )

        layout.addWidget(self.titleLabel)
        layout.addSpacing(12)
        layout.addWidget(self.statusLabel)
        layout.addSpacing(8)
        layout.addWidget(self.hintLabel)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
        painter.end()
        super().paintEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def startDownload(self):
        """启动后台下载线程。"""
        rclone_path = get_rclone_path()
        app_logger.info(f"开始后台下载 rclone: {rclone_path}")

        self._worker = RCloneDownloadWorker(rclone_path, self)
        self._worker.finished.connect(self._onDownloadFinished)
        self._worker.start()

    def _onDownloadFinished(self, success: bool, error_msg: str):
        if success:
            app_logger.info("rclone 下载完成")
        else:
            app_logger.error(f"rclone 下载失败: {error_msg}")
        self.downloadFinished.emit(success, error_msg)
        self.hide()
        self.deleteLater()

    def mousePressEvent(self, event):
        # 拦截所有鼠标事件，阻止穿透到下层
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        # 拦截所有键盘事件
        event.accept()
