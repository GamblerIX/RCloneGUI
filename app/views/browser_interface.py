from PySide6.QtCore import Qt, QModelIndex, QSize, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog
)
import urllib.parse

from qfluentwidgets import (
    ScrollArea, FluentIcon as FIF, IconWidget,
    TitleLabel, BodyLabel, CaptionLabel, PrimaryPushButton,
    PushButton, TransparentPushButton, ComboBox, LineEdit,
    InfoBar, InfoBarPosition, MessageBox, TreeWidget, ToolButton
)

from ..core.rclone import RClone
from ..core.config_manager import ConfigManager
from ..common.signal_bus import signalBus
from ..common.logger import get_logger

logger = get_logger('browser')


class FileListWorker(QThread):
    finished = Signal(bool, list, str)

    def __init__(self, rclone: RClone, remote_path: str):
        super().__init__()
        self.rclone = rclone
        self.remote_path = remote_path
        self._cancelled = False

    def run(self):
        if self._cancelled:
            self.finished.emit(False, [], "操作已取消")
            return

        success, files = self.rclone.lsjson(self.remote_path)

        if self._cancelled:
            self.finished.emit(False, [], "操作已取消")
            return

        if success:
            self.finished.emit(True, files, "")
        else:
            self.finished.emit(False, [], str(files) if isinstance(files, str) else "无法加载文件列表")

    def cancel(self):
        self._cancelled = True
        if not self.isFinished():
            self.wait(1000)


class FileOperationWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, rclone: RClone, operations: list):
        super().__init__()
        self.rclone = rclone
        self.operations = operations
        self._cancelled = False

    def run(self):
        for op in self.operations:
            if self._cancelled:
                self.finished.emit(False, "操作已取消")
                return

            operation = op[0]
            args = op[1:]
            self.progress.emit(f"正在执行: {operation}...")

            if operation == 'copy':
                result = self.rclone.copy(*args)
            elif operation == 'mkdir':
                result = self.rclone.mkdir(*args)
            elif operation == 'purge':
                result = self.rclone.purge(*args)
            elif operation == 'delete_file':
                result = self.rclone.delete_file(*args)
            else:
                self.finished.emit(False, f"未知操作: {operation}")
                return

            if not result.success:
                self.finished.emit(False, result.stderr)
                return

        self.finished.emit(True, "操作完成")

    def cancel(self):
        self._cancelled = True
        if not self.isFinished():
            self.wait(1000)


class BrowserInterface(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('browserInterface')

        self.rclone = RClone()
        self.configManager = ConfigManager(self.rclone)
        self.currentRemote = ''
        self.currentPath = ''
        self._current_worker = None

        self.initUI()
        self.loadRemotes()
        self.connectSignals()

    def connectSignals(self):
        signalBus.remoteAdded.connect(self.onRemoteChanged_signal)
        signalBus.remoteRemoved.connect(self.onRemoteRemoved)
        signalBus.remoteUpdated.connect(self.onRemoteChanged_signal)

    def onRemoteChanged_signal(self, name: str):
        logger.info(f'检测到远程存储变更: {name}，刷新文件浏览器')
        self.loadRemotes()

    def onRemoteRemoved(self, name: str):
        logger.info(f'检测到远程存储被删除: {name}，更新文件浏览器')
        if self.currentRemote == name:
            logger.info(f'当前浏览的远程存储 {name} 已被删除，重置浏览状态')
            self.currentRemote = ''
            self.currentPath = ''
            self.pathEdit.setText('/')
            self.fileTree.clear()
        self.loadRemotes()

    def initUI(self):
        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(36, 20, 36, 20)
        self.mainLayout.setSpacing(16)

        self.titleLabel = TitleLabel('文件浏览', self)
        self.mainLayout.addWidget(self.titleLabel)

        toolbarLayout = QHBoxLayout()

        self.remoteCombo = ComboBox(self)
        self.remoteCombo.setMinimumWidth(200)
        self.remoteCombo.currentIndexChanged.connect(self.onRemoteChanged)

        self.pathEdit = LineEdit(self)
        self.pathEdit.setPlaceholderText('/')
        self.pathEdit.returnPressed.connect(self.navigateToPath)

        self.upBtn = ToolButton(FIF.UP, self)
        self.upBtn.setFixedSize(32, 32)
        self.upBtn.clicked.connect(self.goUp)

        self.refreshBtn = ToolButton(FIF.SYNC, self)
        self.refreshBtn.setFixedSize(32, 32)
        self.refreshBtn.clicked.connect(self.refresh)

        self.homeBtn = ToolButton(FIF.HOME, self)
        self.homeBtn.setFixedSize(32, 32)
        self.homeBtn.clicked.connect(self.goHome)

        toolbarLayout.addWidget(self.remoteCombo)
        toolbarLayout.addWidget(self.homeBtn)
        toolbarLayout.addWidget(self.upBtn)
        toolbarLayout.addWidget(self.pathEdit, 1)
        toolbarLayout.addWidget(self.refreshBtn)

        self.mainLayout.addLayout(toolbarLayout)

        actionLayout = QHBoxLayout()

        self.uploadBtn = PushButton(FIF.UP, '上传', self)
        self.uploadBtn.clicked.connect(self.uploadFile)

        self.downloadBtn = PushButton(FIF.DOWN, '下载', self)
        self.downloadBtn.clicked.connect(self.downloadFile)

        self.newFolderBtn = PushButton(FIF.FOLDER_ADD, '新建文件夹', self)
        self.newFolderBtn.clicked.connect(self.createFolder)

        self.deleteBtn = PushButton(FIF.DELETE, '删除', self)
        self.deleteBtn.clicked.connect(self.deleteSelected)

        actionLayout.addWidget(self.uploadBtn)
        actionLayout.addWidget(self.downloadBtn)
        actionLayout.addWidget(self.newFolderBtn)
        actionLayout.addWidget(self.deleteBtn)
        actionLayout.addStretch()

        self.mainLayout.addLayout(actionLayout)

        self.fileTree = TreeWidget(self)
        self.fileTree.setHeaderLabels(['名称', '大小', '修改时间'])
        self.fileTree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.fileTree.itemDoubleClicked.connect(self.onItemDoubleClicked)

        header = self.fileTree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.mainLayout.addWidget(self.fileTree, 1)

        self._loading_item = None

    def loadRemotes(self):
        self.remoteCombo.blockSignals(True)
        self.remoteCombo.clear()
        self.configManager.refresh()
        remotes = self.configManager.list_remotes()

        for remote in remotes:
            self.remoteCombo.addItem(remote.name)
        self.remoteCombo.blockSignals(False)

        if remotes:
            self.currentRemote = remotes[0].name
            self.refresh()

    def onRemoteChanged(self, index):
        self.currentRemote = self.remoteCombo.currentText()
        self.currentPath = ''
        self.pathEdit.setText('/')
        self.refresh()

    def navigateToPath(self):
        self.currentPath = self.pathEdit.text().strip('/')
        self.refresh()

    def goUp(self):
        if self.currentPath:
            parts = self.currentPath.rstrip('/').split('/')
            self.currentPath = '/'.join(parts[:-1])
            self.pathEdit.setText('/' + self.currentPath)
            self.refresh()

    def goHome(self):
        self.currentPath = ''
        self.pathEdit.setText('/')
        self.refresh()

    def _set_loading_state(self, loading: bool):
        self.fileTree.setEnabled(not loading)
        self.refreshBtn.setEnabled(not loading)
        self.remoteCombo.setEnabled(not loading)

    def _cancel_current_worker(self):
        """安全取消并清理当前 worker，防止访问已销毁的 C++ 对象"""
        worker = self._current_worker
        self._current_worker = None
        if worker is None:
            return
        try:
            if worker.isRunning():
                worker.cancel()
                worker.wait(3000)
            if not worker.isRunning():
                worker.deleteLater()
            else:
                # 线程仍在运行（subprocess 阻塞中），让它结束后自行清理
                logger.warning('[浏览器] worker 线程仍在运行，等待自然结束后清理')
                worker.finished.connect(worker.deleteLater)
        except RuntimeError:
            pass

    def refresh(self):
        if not self.currentRemote:
            return

        self._cancel_current_worker()

        self.fileTree.clear()
        remote_path = self._build_remote_path(self.currentRemote, self.currentPath)

        self._set_loading_state(True)
        self._loading_item = QTreeWidgetItem()
        self._loading_item.setText(0, "加载中...")
        self._loading_item.setIcon(0, FIF.SYNC.icon())
        self.fileTree.addTopLevelItem(self._loading_item)

        self._current_worker = FileListWorker(self.rclone, remote_path)
        self._current_worker.finished.connect(self._on_refresh_finished)
        self._current_worker.finished.connect(self._clear_worker_ref)
        self._current_worker.start()

    def _clear_worker_ref(self, *args):
        """finished 信号回调：清空 worker 引用并安排销毁"""
        worker = self._current_worker
        self._current_worker = None
        if worker is not None:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass

    def _build_remote_path(self, remote_name: str, path: str) -> str:
        if not remote_name or '..' in remote_name or '/' in remote_name or '\\' in remote_name:
            raise ValueError(f"Invalid remote name: {remote_name}")

        if path:
            path_parts = path.replace('\\', '/').split('/')
            safe_parts = []
            for part in path_parts:
                if part == '..' or part == '.':
                    continue
                if part:
                    safe_parts.append(part)
            safe_path = '/'.join(safe_parts)
        else:
            safe_path = ''

        return f'{remote_name}:{safe_path}'

    def _on_refresh_finished(self, success: bool, files: list, error_message: str):
        self._set_loading_state(False)
        self.fileTree.clear()

        if not success:
            logger.error(f'文件列表加载失败: remote={self.currentRemote}, path={self.currentPath}, error={error_message}')
            InfoBar.error('错误', error_message,
                         parent=self, position=InfoBarPosition.TOP)
            return

        logger.debug(f'文件列表加载成功: remote={self.currentRemote}, path={self.currentPath}, count={len(files)}')
        for file in files:
            item = QTreeWidgetItem()
            item.setText(0, file.get('Name', ''))
            item.setData(0, Qt.UserRole, file)

            if file.get('IsDir'):
                item.setIcon(0, FIF.FOLDER.icon())
                item.setText(1, '-')
            else:
                item.setIcon(0, FIF.DOCUMENT.icon())
                size = file.get('Size', 0)
                item.setText(1, self.formatSize(size))

            mod_time = file.get('ModTime', '')
            if mod_time:
                item.setText(2, mod_time[:19].replace('T', ' '))

            self.fileTree.addTopLevelItem(item)

    def formatSize(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} PB'

    def onItemDoubleClicked(self, item: QTreeWidgetItem, column: int):
        file_data = item.data(0, Qt.UserRole)
        if file_data and file_data.get('IsDir'):
            name = file_data.get('Name', '')
            if self.currentPath:
                self.currentPath = f'{self.currentPath}/{name}'
            else:
                self.currentPath = name
            self.pathEdit.setText('/' + self.currentPath)
            self.refresh()

    def uploadFile(self):
        files, _ = QFileDialog.getOpenFileNames(self, '选择文件')
        if not files:
            return

        logger.info(f'用户上传 {len(files)} 个文件到 {self.currentRemote}:{self.currentPath}')
        remote_path = self._build_remote_path(self.currentRemote, self.currentPath)
        operations = [('copy', file, remote_path) for file in files]

        self._execute_operations(operations, f'已上传 {len(files)} 个文件', '上传失败')

    def downloadFile(self):
        items = self.fileTree.selectedItems()
        if not items:
            InfoBar.warning('提示', '请选择要下载的文件',
                           parent=self, position=InfoBarPosition.TOP)
            return

        folder = QFileDialog.getExistingDirectory(self, '选择保存位置')
        if not folder:
            return

        logger.info(f'用户下载 {len(items)} 个文件到 {folder}')
        operations = []
        for item in items:
            file_data = item.data(0, Qt.UserRole)
            if file_data:
                name = file_data.get('Name', '')
                item_path = f"{self.currentPath}/{name}" if self.currentPath else name
                remote_path = self._build_remote_path(self.currentRemote, item_path)
                operations.append(('copy', remote_path, folder))

        self._execute_operations(operations, f'已下载 {len(items)} 个文件', '下载失败')

    def _execute_operations(self, operations: list, success_msg: str, error_prefix: str):
        self._set_loading_state(True)

        self._cancel_current_worker()

        self._current_worker = FileOperationWorker(self.rclone, operations)
        self._current_worker.finished.connect(
            lambda success, msg: self._on_operation_finished(success, msg, success_msg, error_prefix)
        )
        self._current_worker.finished.connect(self._clear_operation_worker_ref)
        self._current_worker.progress.connect(self._on_operation_progress)
        self._current_worker.start()

    def _clear_operation_worker_ref(self, *args):
        """FileOperationWorker finished 回调：清空引用并安排销毁"""
        worker = self._current_worker
        self._current_worker = None
        if worker is not None:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass

    def _on_operation_progress(self, message: str):
        InfoBar.info(
            '进度',
            message,
            parent=self,
            position=InfoBarPosition.TOP,
            duration=1000
        )

    def _on_operation_finished(self, success: bool, message: str, success_msg: str, error_prefix: str):
        self._set_loading_state(False)

        if success:
            logger.info(f'文件操作成功: {success_msg}')
            InfoBar.success('成功', success_msg,
                           parent=self, position=InfoBarPosition.TOP)
            # 延迟到下一个事件循环再 refresh，避免在 worker 的 finished 信号
            # 处理链中调用 _cancel_current_worker 导致 C++ 对象被提前销毁而崩溃
            QTimer.singleShot(0, self.refresh)
        else:
            logger.error(f'文件操作失败: {error_prefix} - {message}')
            InfoBar.error(error_prefix, message,
                         parent=self, position=InfoBarPosition.TOP)

    def createFolder(self):
        dialog = MessageBox('新建文件夹', '', self.window())
        nameEdit = LineEdit(dialog)
        nameEdit.setPlaceholderText('文件夹名称')
        dialog.textLayout.addWidget(nameEdit)

        if dialog.exec():
            name = nameEdit.text().strip()
            if name:
                if '/' in name or '\\' in name or '..' in name:
                    logger.warning(f'用户创建文件夹失败: 名称包含非法字符 "{name}"')
                    InfoBar.error('错误', '文件夹名称包含非法字符',
                                 parent=self, position=InfoBarPosition.TOP)
                    return
                logger.info(f'用户创建文件夹: {self.currentRemote}:{self.currentPath}/{name}')
                item_path = f"{self.currentPath}/{name}" if self.currentPath else name
                remote_path = self._build_remote_path(self.currentRemote, item_path)
                self._execute_operations(
                    [('mkdir', remote_path)],
                    f'已创建文件夹: {name}',
                    '创建失败'
                )

    def deleteSelected(self):
        items = self.fileTree.selectedItems()
        if not items:
            InfoBar.warning('提示', '请选择要删除的文件',
                           parent=self, position=InfoBarPosition.TOP)
            return

        names = [item.data(0, Qt.UserRole).get('Name', '') for item in items]
        box = MessageBox('确认删除', f'确定要删除 {len(items)} 个项目吗？\n{", ".join(names[:3])}...', self.window())

        if box.exec():
            logger.info(f'用户确认删除 {len(items)} 个项目: {names[:3]}')
            operations = []
            for item in items:
                file_data = item.data(0, Qt.UserRole)
                if file_data:
                    name = file_data.get('Name', '')
                    item_path = f"{self.currentPath}/{name}" if self.currentPath else name
                    remote_path = self._build_remote_path(self.currentRemote, item_path)

                    if file_data.get('IsDir'):
                        operations.append(('purge', remote_path))
                    else:
                        operations.append(('delete_file', remote_path))

            self._execute_operations(operations, f'已删除 {len(items)} 个项目', '删除失败')
