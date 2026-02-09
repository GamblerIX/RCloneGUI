from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
)

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False

from qfluentwidgets import (
    ScrollArea, FluentIcon as FIF, IconWidget,
    TitleLabel, BodyLabel, StrongBodyLabel, CaptionLabel, PrimaryPushButton,
    PushButton, TransparentPushButton, SimpleCardWidget,
    MessageBox, ComboBox, Dialog, LineEdit, ProgressBar,
    InfoBar, InfoBarPosition, SwitchButton, isDarkTheme
)

from ..common.signal_bus import signalBus
from ..common.logger import get_logger
from ..core.rclone import RClone
from ..core.config_manager import ConfigManager
from ..core.sync_manager import SyncManager
from ..models.sync_task import SyncTask, SyncMode, SyncStatus

logger = get_logger('sync')


class SyncTaskCard(SimpleCardWidget):

    runClicked = Signal(str)
    stopClicked = Signal(str)
    editClicked = Signal(str)
    deleteClicked = Signal(str)

    def __init__(self, task: SyncTask, parent=None):
        super().__init__(parent)
        self.task = task
        self.setFixedHeight(100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)

        self.iconWidget = IconWidget(FIF.SYNC, self)
        self.iconWidget.setFixedSize(40, 40)

        infoLayout = QVBoxLayout()
        infoLayout.setSpacing(2)
        self.nameLabel = StrongBodyLabel(task.name or f'任务 {task.id}', self)

        mode_text = {'sync': '同步', 'copy': '复制', 'move': '移动', 'bisync': '双向同步'}
        self.infoLabel = CaptionLabel(
            f'{mode_text.get(task.mode.value, task.mode.value)}: {task.source} → {task.destination}',
            self
        )

        status_text = {
            SyncStatus.IDLE: '空闲',
            SyncStatus.RUNNING: '运行中',
            SyncStatus.PAUSED: '已暂停',
            SyncStatus.COMPLETED: '已完成',
            SyncStatus.ERROR: '错误'
        }
        self.statusLabel = CaptionLabel(status_text.get(task.status, '未知'), self)

        infoLayout.addWidget(self.nameLabel)
        infoLayout.addWidget(self.infoLabel)
        infoLayout.addWidget(self.statusLabel)

        self.progressBar = ProgressBar(self)
        self.progressBar.setFixedWidth(100)
        self.progressBar.setValue(task.progress)
        self.progressBar.setVisible(task.status == SyncStatus.RUNNING)

        btnLayout = QHBoxLayout()
        btnLayout.setSpacing(8)

        self.actionBtn = PrimaryPushButton('运行', self)
        self.actionBtn.setFixedWidth(70)
        self._updateButton()

        self.editBtn = TransparentPushButton('编辑', self)
        self.editBtn.setFixedWidth(60)
        self.editBtn.clicked.connect(lambda: self.editClicked.emit(task.id))

        self.deleteBtn = TransparentPushButton('删除', self)
        self.deleteBtn.setFixedWidth(60)
        self.deleteBtn.clicked.connect(lambda: self.deleteClicked.emit(task.id))

        btnLayout.addWidget(self.progressBar)
        btnLayout.addWidget(self.actionBtn)
        btnLayout.addWidget(self.editBtn)
        btnLayout.addWidget(self.deleteBtn)

        layout.addWidget(self.iconWidget)
        layout.addSpacing(16)
        layout.addLayout(infoLayout, 1)
        layout.addLayout(btnLayout)

    def updateProgress(self, progress: int):
        self.progressBar.setValue(progress)
        self.progressBar.setVisible(True)

    def updateStatus(self, status: SyncStatus):
        self.task.status = status
        status_text = {
            SyncStatus.IDLE: '空闲',
            SyncStatus.RUNNING: '运行中',
            SyncStatus.PAUSED: '已暂停',
            SyncStatus.COMPLETED: '已完成',
            SyncStatus.ERROR: '错误'
        }
        self.statusLabel.setText(status_text.get(status, '未知'))
        self.progressBar.setVisible(status == SyncStatus.RUNNING)
        self._updateButton()

    def _updateButton(self):
        self.actionBtn.blockSignals(True)

        try:
            if hasattr(self, '_current_action_handler'):
                self.actionBtn.clicked.disconnect(self._current_action_handler)
        except (TypeError, RuntimeError):
            pass

        if self.task.status == SyncStatus.RUNNING:
            self.actionBtn.setText('停止')
            self._current_action_handler = lambda: self.stopClicked.emit(self.task.id)
        else:
            self.actionBtn.setText('运行')
            self._current_action_handler = lambda: self.runClicked.emit(self.task.id)

        self.actionBtn.clicked.connect(self._current_action_handler)
        self.actionBtn.blockSignals(False)


class AddSyncDialog(Dialog):

    def __init__(self, remotes: list, parent=None, task: SyncTask = None):
        self.task = task
        self.remotes = remotes
        title = '编辑同步任务' if task else '添加同步任务'
        super().__init__(title, '', parent)

        self.setFixedSize(500, 520)
        self.initUI()

        if task:
            self.loadTask(task)

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
        layout.setSpacing(12)
        layout.setContentsMargins(24, 0, 24, 0)

        layout.addWidget(QLabel('任务名称:'))
        self.nameEdit = LineEdit(self)
        layout.addWidget(self.nameEdit)

        layout.addWidget(QLabel('同步模式:'))
        self.modeCombo = ComboBox(self)
        self.modeCombo.addItem('同步 (使目标与源完全一致)', SyncMode.SYNC)
        self.modeCombo.addItem('复制 (仅复制文件)', SyncMode.COPY)
        self.modeCombo.addItem('移动 (移动后删除源)', SyncMode.MOVE)
        self.modeCombo.addItem('双向同步 (Bisync)', SyncMode.BISYNC)
        layout.addWidget(self.modeCombo)

        layout.addWidget(QLabel('源路径:'))
        sourceLayout = QHBoxLayout()
        self.sourceEdit = LineEdit(self)
        self.sourceEdit.setPlaceholderText('本地路径或 remote:path')
        self.sourceBrowseBtn = PushButton('...', self)
        self.sourceBrowseBtn.setFixedWidth(40)
        self.sourceBrowseBtn.clicked.connect(lambda: self.browseLocal(self.sourceEdit))
        sourceLayout.addWidget(self.sourceEdit, 1)
        sourceLayout.addWidget(self.sourceBrowseBtn)
        layout.addLayout(sourceLayout)

        layout.addWidget(QLabel('目标路径:'))
        destLayout = QHBoxLayout()
        self.destEdit = LineEdit(self)
        self.destEdit.setPlaceholderText('本地路径或 remote:path')
        self.destBrowseBtn = PushButton('...', self)
        self.destBrowseBtn.setFixedWidth(40)
        self.destBrowseBtn.clicked.connect(lambda: self.browseLocal(self.destEdit))
        destLayout.addWidget(self.destEdit, 1)
        destLayout.addWidget(self.destBrowseBtn)
        layout.addLayout(destLayout)

        layout.addWidget(QLabel('快速选择远程:'))
        remoteLayout = QHBoxLayout()
        self.remoteCombo = ComboBox(self)
        self.remoteCombo.addItem('选择远程存储...')
        for remote in self.remotes:
            self.remoteCombo.addItem(remote.name)

        self.toSourceBtn = PushButton('→ 源', self)
        self.toSourceBtn.clicked.connect(lambda: self.applyRemote(self.sourceEdit))
        self.toDestBtn = PushButton('→ 目标', self)
        self.toDestBtn.clicked.connect(lambda: self.applyRemote(self.destEdit))

        remoteLayout.addWidget(self.remoteCombo, 1)
        remoteLayout.addWidget(self.toSourceBtn)
        remoteLayout.addWidget(self.toDestBtn)
        layout.addLayout(remoteLayout)

        layout.addSpacing(10)
        scheduleHeader = QHBoxLayout()
        scheduleHeader.addWidget(QLabel('定时同步:'))
        self.scheduleSwitch = SwitchButton(self)
        self.scheduleSwitch.setChecked(False)
        self.scheduleSwitch.checkedChanged.connect(self.onScheduleToggled)
        scheduleHeader.addStretch()
        scheduleHeader.addWidget(self.scheduleSwitch)
        layout.addLayout(scheduleHeader)

        self.schedulePresetCombo = ComboBox(self)
        self.schedulePresetCombo.setEnabled(False)
        self.schedulePresetCombo.addItem('自定义', '')
        self.schedulePresetCombo.addItem('每天凌晨 2 点', '0 2 * * *')
        self.schedulePresetCombo.addItem('每天中午 12 点', '0 12 * * *')
        self.schedulePresetCombo.addItem('每天晚上 8 点', '0 20 * * *')
        self.schedulePresetCombo.addItem('每 6 小时', '0 */6 * * *')
        self.schedulePresetCombo.addItem('每 12 小时', '0 */12 * * *')
        self.schedulePresetCombo.addItem('每周日午夜', '0 0 * * 0')
        self.schedulePresetCombo.addItem('每月 1 号', '0 0 1 * *')
        self.schedulePresetCombo.currentIndexChanged.connect(self.onPresetChanged)
        layout.addWidget(self.schedulePresetCombo)

        cronLayout = QHBoxLayout()
        self.cronEdit = LineEdit(self)
        self.cronEdit.setEnabled(False)
        self.cronEdit.setPlaceholderText('Cron 表达式 (如 0 2 * * *)')
        self.cronEdit.textChanged.connect(self.validateCron)
        cronLayout.addWidget(QLabel('表达式:'))
        cronLayout.addWidget(self.cronEdit, 1)
        layout.addLayout(cronLayout)

        self.nextRunLabel = CaptionLabel('下次运行: -', self)
        self.nextRunLabel.setEnabled(False)
        layout.addWidget(self.nextRunLabel)

        self.cronStatusLabel = CaptionLabel('', self)
        layout.addWidget(self.cronStatusLabel)

        layout.addSpacing(10)
        layout.addWidget(QLabel('高级选项:'))

        bwLayout = QHBoxLayout()
        bwLayout.addWidget(QLabel('带宽限制:'))
        self.bwLimitEdit = LineEdit(self)
        self.bwLimitEdit.setPlaceholderText('如: 10M, 100k (留空表示不限速)')
        bwLayout.addWidget(self.bwLimitEdit, 1)
        layout.addLayout(bwLayout)

        layout.addWidget(QLabel('排除模式 (每行一个,支持通配符):'))
        from PySide6.QtWidgets import QTextEdit
        self.excludeEdit = QTextEdit(self)
        self.excludeEdit.setPlaceholderText('*.tmp\n*.log\n.DS_Store')
        self.excludeEdit.setMaximumHeight(80)
        layout.addWidget(self.excludeEdit)

        dryRunLayout = QHBoxLayout()
        dryRunLayout.addWidget(QLabel('仅预览 (不实际执行):'))
        self.dryRunSwitch = SwitchButton(self)
        self.dryRunSwitch.setChecked(False)
        dryRunLayout.addStretch()
        dryRunLayout.addWidget(self.dryRunSwitch)
        layout.addLayout(dryRunLayout)

        deleteExcludedLayout = QHBoxLayout()
        deleteExcludedLayout.addWidget(QLabel('删除目标端被排除的文件:'))
        self.deleteExcludedSwitch = SwitchButton(self)
        self.deleteExcludedSwitch.setChecked(False)
        deleteExcludedLayout.addStretch()
        deleteExcludedLayout.addWidget(self.deleteExcludedSwitch)
        layout.addLayout(deleteExcludedLayout)

        self.vBoxLayout.insertLayout(button_index, layout)

        # 在自定义内容和按钮栏之间插入弹性空间
        new_button_index = self.vBoxLayout.indexOf(self.buttonGroup)
        self.vBoxLayout.insertStretch(new_button_index, 1)

        # 按钮文本汉化
        self.yesButton.setText('确认')
        self.cancelButton.setText('取消')

    def browseLocal(self, edit: LineEdit):
        folder = QFileDialog.getExistingDirectory(self, '选择文件夹')
        if folder:
            edit.setText(folder)

    def applyRemote(self, edit: LineEdit):
        if self.remoteCombo.currentIndex() > 0:
            remote = self.remoteCombo.currentText()
            edit.setText(f'{remote}:')

    def onScheduleToggled(self, enabled: bool):
        self.schedulePresetCombo.setEnabled(enabled)
        self.cronEdit.setEnabled(enabled)
        self.nextRunLabel.setEnabled(enabled)
        if not enabled:
            self.cronEdit.clear()
            self.nextRunLabel.setText('下次运行: -')
            self.cronStatusLabel.setText('')

    def onPresetChanged(self, index: int):
        preset = self.schedulePresetCombo.currentData()
        if preset:
            self.cronEdit.setText(preset)

    def validateCron(self, expression: str):
        if not expression.strip():
            self.cronStatusLabel.setText('')
            self.nextRunLabel.setText('下次运行: -')
            return

        if not CRONITER_AVAILABLE:
            self.cronStatusLabel.setText('⚠️ croniter 模块未安装')
            self.cronStatusLabel.setStyleSheet(f'color: {"#e8a838" if isDarkTheme() else "orange"};')
            return

        try:
            croniter(expression)
            self.cronStatusLabel.setText('✓ 有效')
            self.cronStatusLabel.setStyleSheet(f'color: {"#70c070" if isDarkTheme() else "green"};')

            itr = croniter(expression)
            next_run = itr.get_next(datetime)
            self.nextRunLabel.setText(f'下次运行: {next_run.strftime("%Y-%m-%d %H:%M")}')
        except Exception as e:
            self.cronStatusLabel.setText(f'✗ 无效: {str(e)}')
            self.cronStatusLabel.setStyleSheet(f'color: {"#ff6b6b" if isDarkTheme() else "red"};')
            self.nextRunLabel.setText('下次运行: -')

    def loadTask(self, task: SyncTask):
        self.nameEdit.setText(task.name)
        self.sourceEdit.setText(task.source)
        self.destEdit.setText(task.destination)

        for i in range(self.modeCombo.count()):
            if self.modeCombo.itemData(i) == task.mode:
                self.modeCombo.setCurrentIndex(i)
                break

        self.scheduleSwitch.setChecked(task.scheduled)
        if task.scheduled and task.cron_expression:
            self.cronEdit.setText(task.cron_expression)
            preset_found = False
            for i in range(self.schedulePresetCombo.count()):
                if self.schedulePresetCombo.itemData(i) == task.cron_expression:
                    self.schedulePresetCombo.setCurrentIndex(i)
                    preset_found = True
                    break
            if not preset_found:
                self.schedulePresetCombo.setCurrentIndex(0)

        self.bwLimitEdit.setText(task.bandwidth_limit)
        self.excludeEdit.setPlainText('\n'.join(task.exclude_patterns))
        self.dryRunSwitch.setChecked(task.dry_run)
        self.deleteExcludedSwitch.setChecked(task.delete_excluded)

    def getData(self) -> dict:
        exclude_text = self.excludeEdit.toPlainText().strip()
        exclude_patterns = [p.strip() for p in exclude_text.split('\n') if p.strip()]

        return {
            'name': self.nameEdit.text().strip(),
            'source': self.sourceEdit.text().strip(),
            'destination': self.destEdit.text().strip(),
            'mode': self.modeCombo.currentData() or SyncMode.SYNC,
            'scheduled': self.scheduleSwitch.isChecked(),
            'cron_expression': self.cronEdit.text().strip() if self.scheduleSwitch.isChecked() else '',
            'bandwidth_limit': self.bwLimitEdit.text().strip(),
            'exclude_patterns': exclude_patterns,
            'dry_run': self.dryRunSwitch.isChecked(),
            'delete_excluded': self.deleteExcludedSwitch.isChecked()
        }


class SyncInterface(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('syncInterface')
        self.setWidgetResizable(True)

        self.rclone = RClone()
        self.configManager = ConfigManager(self.rclone)
        self.syncManager = SyncManager(self.rclone)

        self.taskCards: dict = {}

        self.initUI()
        self.connectSignals()
        self.loadTasks()

    def initUI(self):
        self.scrollWidget = QWidget()
        self.setWidget(self.scrollWidget)
        self.enableTransparentBackground()

        self.mainLayout = QVBoxLayout(self.scrollWidget)
        self.mainLayout.setContentsMargins(36, 20, 36, 20)
        self.mainLayout.setSpacing(16)

        headerLayout = QHBoxLayout()
        self.titleLabel = TitleLabel('同步任务', self)
        self.addBtn = PrimaryPushButton(FIF.ADD, '添加', self)
        self.addBtn.clicked.connect(self.showAddDialog)

        headerLayout.addWidget(self.titleLabel)
        headerLayout.addStretch()
        headerLayout.addWidget(self.addBtn)

        self.mainLayout.addLayout(headerLayout)

        self.listWidget = QWidget()
        self.listLayout = QVBoxLayout(self.listWidget)
        self.listLayout.setContentsMargins(0, 0, 0, 0)
        self.listLayout.setSpacing(8)

        self.mainLayout.addWidget(self.listWidget)
        self.mainLayout.addStretch()

    def connectSignals(self):
        self.syncManager.taskStatusChanged.connect(self.onTaskStatusChanged)
        self.syncManager.taskProgress.connect(self.onTaskProgress)
        self.syncManager.taskError.connect(self.onTaskError)

    def loadTasks(self):
        while self.listLayout.count():
            item = self.listLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.taskCards.clear()

        if not self.syncManager.tasks:
            emptyLabel = CaptionLabel('暂无同步任务，点击"添加"创建', self)
            emptyLabel.setAlignment(Qt.AlignCenter)
            self.listLayout.addWidget(emptyLabel)
            return

        for task in self.syncManager.tasks.values():
            card = SyncTaskCard(task, self)
            card.runClicked.connect(self.runTask)
            card.stopClicked.connect(self.stopTask)
            card.editClicked.connect(self.showEditDialog)
            card.deleteClicked.connect(self.deleteTask)
            self.listLayout.addWidget(card)
            self.taskCards[task.id] = card

    def showAddDialog(self):
        self.configManager.refresh()
        remotes = self.configManager.list_remotes()

        dialog = AddSyncDialog(remotes, self)
        if dialog.exec():
            data = dialog.getData()
            if data['source'] and data['destination']:
                logger.info(f'用户添加同步任务: {data["name"]}, {data["source"]} → {data["destination"]}, mode={data["mode"].value}')
                task = self.syncManager.add_task(**data)
                if data.get('scheduled') and data.get('cron_expression'):
                    success = self.syncManager.enable_schedule(
                        task.id, data['cron_expression']
                    )
                    if not success:
                        logger.warning(f'定时表达式无效: {data["cron_expression"]}')
                        InfoBar.warning(
                            '警告',
                            '定时表达式无效，任务已添加但未启用定时',
                            parent=self,
                            position=InfoBarPosition.TOP
                        )
                self.loadTasks()
                logger.info(f'同步任务添加成功: {task.id}')
                InfoBar.success('成功', '已添加同步任务',
                               parent=self, position=InfoBarPosition.TOP)

    def showEditDialog(self, task_id: str):
        logger.info(f'用户打开编辑同步任务对话框: {task_id}')
        task = self.syncManager.tasks.get(task_id)
        if not task:
            logger.warning(f'未找到同步任务: {task_id}')
            return

        self.configManager.refresh()
        remotes = self.configManager.list_remotes()

        dialog = AddSyncDialog(remotes, self, task)
        if dialog.exec():
            data = dialog.getData()
            logger.info(f'用户更新同步任务: {task_id}, {data["source"]} → {data["destination"]}')
            task.name = data['name']
            task.source = data['source']
            task.destination = data['destination']
            task.mode = data['mode']

            if data.get('scheduled') and data.get('cron_expression'):
                self.syncManager.enable_schedule(task_id, data['cron_expression'])
            else:
                self.syncManager.disable_schedule(task_id)

            task.bandwidth_limit = data.get('bandwidth_limit', '')
            task.exclude_patterns = data.get('exclude_patterns', [])
            task.dry_run = data.get('dry_run', False)
            task.delete_excluded = data.get('delete_excluded', False)

            self.syncManager.save_tasks()
            self.loadTasks()

    def deleteTask(self, task_id: str):
        logger.info(f'用户请求删除同步任务: {task_id}')
        box = MessageBox('确认删除', '确定要删除该同步任务吗？', self.window())
        if box.exec():
            logger.info(f'用户确认删除同步任务: {task_id}')
            self.syncManager.remove_task(task_id)
            logger.info(f'同步任务已删除: {task_id}')
            self.loadTasks()
        else:
            logger.info(f'用户取消删除同步任务: {task_id}')

    def runTask(self, task_id: str):
        logger.info(f'用户启动同步任务: {task_id}')
        self.syncManager.run_task(task_id)

    def stopTask(self, task_id: str):
        logger.info(f'用户停止同步任务: {task_id}')
        self.syncManager.cancel_task(task_id)

    def onTaskStatusChanged(self, task_id: str, status: SyncStatus):
        logger.info(f'同步任务状态变更: {task_id} → {status.name}')
        if task_id in self.taskCards:
            self.taskCards[task_id].updateStatus(status)

    def onTaskProgress(self, task_id: str, progress: int):
        if task_id in self.taskCards:
            self.taskCards[task_id].updateProgress(progress)

    def onTaskError(self, task_id: str, error: str):
        logger.error(f'同步任务失败: {task_id}, error={error}')
        InfoBar.error('同步失败', error,
                     parent=self, position=InfoBarPosition.TOP)
