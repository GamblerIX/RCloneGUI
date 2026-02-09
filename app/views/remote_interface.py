import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QStackedWidget, QLabel, QFrame
)

from qfluentwidgets import (
    ScrollArea, FluentIcon as FIF, CardWidget, IconWidget,
    TitleLabel, BodyLabel, StrongBodyLabel, CaptionLabel, PrimaryPushButton,
    PushButton, TransparentPushButton, SimpleCardWidget,
    MessageBox, LineEdit, PasswordLineEdit, ComboBox,
    Dialog, FluentIcon, InfoBar, InfoBarPosition
)

from ..common.signal_bus import signalBus
from ..common.logger import get_logger
from ..core.rclone import RClone
from ..core.config_manager import ConfigManager
from ..providers import get_all_providers, get_provider
from ..models.remote import Remote

logger = get_logger('remote')


def generate_remote_name(type_display_name: str, existing_names: list[str] = None) -> str:
    """根据类型显示名和已有名称列表生成不重复的远程存储名称。

    将显示名中的特殊字符去除后拼接递增数字，确保名称唯一。

    Args:
        type_display_name: 类型显示名，如 "WebDAV", "SMB / CIFS", "Amazon S3"
        existing_names: 已有远程存储名称列表，为 None 时视为空列表

    Returns:
        不重复的名称字符串，格式为 "{base_name}{n}"
    """
    base_name = re.sub(r'[^a-zA-Z0-9_-]', '', type_display_name)
    if not base_name:
        base_name = "Remote"
    if existing_names is None:
        existing_names = []
    n = 1
    while f"{base_name}{n}" in existing_names:
        n += 1
    return f"{base_name}{n}"


class RemoteCard(SimpleCardWidget):

    editClicked = Signal(str)
    deleteClicked = Signal(str)
    testClicked = Signal(str)

    def __init__(self, remote: Remote, parent=None):
        super().__init__(parent)
        self.remote = remote
        self.setFixedHeight(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)

        self.iconWidget = IconWidget(FIF.CLOUD, self)
        self.iconWidget.setFixedSize(40, 40)

        infoLayout = QVBoxLayout()
        infoLayout.setSpacing(2)
        self.nameLabel = StrongBodyLabel(remote.name, self)
        self.typeLabel = CaptionLabel(f'{remote.type}', self)
        if remote.host:
            self.typeLabel.setText(f'{remote.type} - {remote.host}')
        infoLayout.addWidget(self.nameLabel)
        infoLayout.addWidget(self.typeLabel)

        btnLayout = QHBoxLayout()
        btnLayout.setSpacing(8)

        self.testBtn = TransparentPushButton('测试', self)
        self.testBtn.setFixedWidth(60)
        self.testBtn.clicked.connect(lambda: self.testClicked.emit(remote.name))

        self.editBtn = TransparentPushButton('编辑', self)
        self.editBtn.setFixedWidth(60)
        self.editBtn.clicked.connect(lambda: self.editClicked.emit(remote.name))

        self.deleteBtn = TransparentPushButton('删除', self)
        self.deleteBtn.setFixedWidth(60)
        self.deleteBtn.clicked.connect(lambda: self.deleteClicked.emit(remote.name))

        btnLayout.addWidget(self.testBtn)
        btnLayout.addWidget(self.editBtn)
        btnLayout.addWidget(self.deleteBtn)

        layout.addWidget(self.iconWidget)
        layout.addSpacing(16)
        layout.addLayout(infoLayout, 1)
        layout.addLayout(btnLayout)


class AddRemoteDialog(Dialog):

    def __init__(self, parent=None, remote: Remote = None, existing_names: list[str] = None):
        self.remote = remote
        self._existing_names = existing_names or []
        self._name_manually_edited = False
        title = '编辑远程存储' if remote else '添加远程存储'
        logger.info(f'[对话框] 创建 AddRemoteDialog: mode={"编辑" if remote else "添加"}'
                    f'{f", remote={remote.name}({remote.type})" if remote else ""}')
        super().__init__(title, '', parent)

        self._field_labels = []
        self.initUI()

        if remote:
            self.loadRemote(remote)
        else:
            self._applyAutoName()


    def initUI(self):
        logger.debug('[对话框] initUI 开始')

        # 隐藏 Dialog 基类自带的空内容标签
        if hasattr(self, 'contentLabel'):
            self.contentLabel.hide()
            self.contentLabel.setFixedHeight(0)

        # textLayout 默认 stretch=1 会吞掉多余空间，在标题和名称之间产生空白
        self.vBoxLayout.setStretchFactor(self.textLayout, 0)

        button_index = self.vBoxLayout.indexOf(self.buttonGroup)

        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(24, 0, 24, 0)

        self.nameEdit = LineEdit(self)
        self.nameEdit.setPlaceholderText('远程存储名称 (英文)')
        self.nameEdit.textEdited.connect(lambda _: setattr(self, '_name_manually_edited', True))
        layout.addWidget(QLabel('名称:'))
        layout.addWidget(self.nameEdit)

        self.typeCombo = ComboBox(self)
        for type_id, type_info in get_all_providers().items():
            self.typeCombo.addItem(type_info['name'], userData=type_id)
        self.typeCombo.currentIndexChanged.connect(self.onTypeChanged)
        layout.addWidget(QLabel('类型:'))
        layout.addWidget(self.typeCombo)

        self.fieldsWidget = QWidget()
        self.fieldsLayout = QGridLayout(self.fieldsWidget)
        self.fieldsLayout.setSpacing(10)
        layout.addWidget(self.fieldsWidget)

        self.fieldWidgets = {}
        self._field_labels = []
        self.onTypeChanged(0)

        self.vBoxLayout.insertLayout(button_index, layout)

        # 在自定义字段和按钮栏之间插入弹性空间，吸收多余高度
        # 避免空白出现在标题或名称上方
        new_button_index = self.vBoxLayout.indexOf(self.buttonGroup)
        self.vBoxLayout.insertStretch(new_button_index, 1)

        # 按钮文本汉化
        self.yesButton.setText('确认')
        self.cancelButton.setText('取消')
        logger.debug('[对话框] initUI 完成')

    def _applyAutoName(self):
        """根据当前选中类型自动生成名称并填充到名称字段"""
        type_id = self.typeCombo.currentData()
        provider_config = get_provider(type_id)
        if type_id and provider_config:
            type_display_name = provider_config['name']
            name = generate_remote_name(type_display_name, self._existing_names)
            self.nameEdit.setText(name)
            self._name_manually_edited = False


    def accept(self):
        name = self.nameEdit.text().strip()
        if not name:
            InfoBar.warning('提示', '请填写远程存储名称',
                           parent=self, position=InfoBarPosition.TOP)
            return
        super().accept()

    def _clearFields(self):
        """清理所有动态字段控件"""
        for widget in self.fieldWidgets.values():
            widget.setParent(None)
            widget.deleteLater()
        self.fieldWidgets.clear()

        for label in self._field_labels:
            label.setParent(None)
            label.deleteLater()
        self._field_labels.clear()

        while self.fieldsLayout.count():
            item = self.fieldsLayout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _resizeForFields(self, field_count):
        """根据字段数量动态调整对话框高度，宽度固定 500"""
        base = 280
        height = base + field_count * 50
        self.setFixedSize(500, min(height, 700))

    def onTypeChanged(self, index):
        type_id = self.typeCombo.currentData()
        logger.info(f'[对话框] 类型切换: index={index}, type_id={type_id}')

        self._clearFields()

        provider_config = get_provider(type_id)
        if not provider_config:
            logger.warning(f'[对话框] 未知的远程存储类型: {type_id}')
            return

        fields = provider_config['fields']

        row = 0
        for field_id, field_info in fields.items():
            label = QLabel(f"{field_info['label']}:")
            self._field_labels.append(label)
            self.fieldsLayout.addWidget(label, row, 0)

            if field_info['type'] == 'password':
                widget = PasswordLineEdit(self)
            elif field_info['type'] == 'choice':
                widget = ComboBox(self)
                for choice in field_info.get('choices', []):
                    widget.addItem(choice)
                # 为 S3 的 provider 字段绑定联动
                if type_id == 's3' and field_id == 'provider':
                    widget.currentIndexChanged.connect(self._onS3ProviderChanged)
                # 为 WebDAV 的 vendor 字段绑定联动
                if type_id == 'webdav' and field_id == 'vendor':
                    widget.currentIndexChanged.connect(self._onWebdavVendorChanged)
            else:
                widget = LineEdit(self)
                if 'default' in field_info:
                    widget.setText(str(field_info['default']))

            if field_info.get('readonly'):
                widget.setEnabled(False)

            self.fieldsLayout.addWidget(widget, row, 1)
            self.fieldWidgets[field_id] = widget
            logger.debug(f'[对话框] 添加字段: {field_id} (row={row}, type={field_info["type"]})')
            row += 1

        # S3 类型初始化时触发一次 provider 联动
        if type_id == 's3' and 'provider' in self.fieldWidgets:
            self._onS3ProviderChanged(0)

        # WebDAV 类型初始化时触发一次 vendor 联动
        if type_id == 'webdav' and 'vendor' in self.fieldWidgets:
            self._onWebdavVendorChanged(0)

        logger.info(f'[对话框] 类型切换完成: {type_id}, 共 {row} 个字段')

        # 所有字段添加完成后再调整高度，避免布局引擎在空内容时错误分配空间
        self._resizeForFields(len(fields))

        # 自动命名：如果用户未手动修改名称且非编辑模式，更新名称
        if not self._name_manually_edited and not self.remote:
            self._applyAutoName()

    def _onWebdavVendorChanged(self, index):
        """WebDAV Vendor 切换时动态调整 url 和 user 字段的 placeholder"""
        vendor_widget = self.fieldWidgets.get('vendor')
        if not vendor_widget:
            return

        vendor_name = vendor_widget.currentText()
        type_config = get_provider('webdav') or {}
        vendor_configs = type_config.get('vendor_config', {})
        vcfg = vendor_configs.get(vendor_name, {})

        logger.info(f'[对话框] WebDAV Vendor 切换: {vendor_name}')

        # 更新 url 字段：已知服务商锁定 URL，other 恢复可编辑
        url_widget = self.fieldWidgets.get('url')
        if url_widget and isinstance(url_widget, LineEdit):
            url_cfg = vcfg.get('url', {})
            fixed_url = url_cfg.get('fixed_url')
            is_readonly = url_cfg.get('readonly', False)

            if fixed_url and is_readonly:
                url_widget.setText(fixed_url)
                url_widget.setReadOnly(True)
            else:
                if not self.remote:  # 添加模式才清空
                    url_widget.clear()
                url_widget.setReadOnly(False)
                url_widget.setPlaceholderText(url_cfg.get('placeholder', ''))

        # 更新 user placeholder
        user_widget = self.fieldWidgets.get('user')
        if user_widget and isinstance(user_widget, LineEdit):
            user_cfg = vcfg.get('user', {})
            user_widget.setPlaceholderText(user_cfg.get('placeholder', ''))

    def _onS3ProviderChanged(self, index):
        """S3 Provider 切换时动态调整 region 和 endpoint 字段"""
        provider_widget = self.fieldWidgets.get('provider')
        if not provider_widget:
            return

        provider_name = provider_widget.currentText()
        type_config = get_provider('s3') or {}
        provider_configs = type_config.get('provider_config', {})
        pcfg = provider_configs.get(provider_name, {})

        logger.info(f'[对话框] S3 Provider 切换: {provider_name}')

        region_cfg = pcfg.get('region', {})
        endpoint_cfg = pcfg.get('endpoint', {})

        # --- 处理 region 字段 ---
        region_label = None
        region_row = -1
        old_region = self.fieldWidgets.get('region')
        if old_region:
            # 保存旧值
            if isinstance(old_region, ComboBox):
                old_value = old_region.currentText()
            else:
                old_value = old_region.text().strip()

            # 找到 region 在 grid 中的行
            idx = self.fieldsLayout.indexOf(old_region)
            if idx >= 0:
                region_row, _, _, _ = self.fieldsLayout.getItemPosition(idx)
            # 找到对应的 label
            for lbl in self._field_labels:
                if lbl.text() == '区域:':
                    region_label = lbl
                    break

            old_region.setParent(None)
            old_region.deleteLater()
        else:
            old_value = ''

        if region_row >= 0:
            if region_cfg.get('type') == 'choice':
                new_region = ComboBox(self)
                for choice in region_cfg.get('choices', []):
                    new_region.addItem(choice)
                # 尝试恢复旧值
                restore_idx = new_region.findText(old_value)
                if restore_idx >= 0:
                    new_region.setCurrentIndex(restore_idx)
                elif region_cfg.get('default'):
                    default_idx = new_region.findText(region_cfg['default'])
                    if default_idx >= 0:
                        new_region.setCurrentIndex(default_idx)
            else:
                new_region = LineEdit(self)
                placeholder = region_cfg.get('placeholder', '')
                if placeholder:
                    new_region.setPlaceholderText(placeholder)
                if old_value:
                    new_region.setText(old_value)
                elif region_cfg.get('default'):
                    new_region.setText(str(region_cfg['default']))

            self.fieldsLayout.addWidget(new_region, region_row, 1)
            self.fieldWidgets['region'] = new_region

            # 如果 endpoint 有 auto_format，region 变化时需要联动更新 endpoint
            if endpoint_cfg.get('auto_format'):
                if isinstance(new_region, ComboBox):
                    new_region.currentIndexChanged.connect(
                        lambda _: self._updateAutoEndpoint(endpoint_cfg['auto_format']))
                else:
                    new_region.textChanged.connect(
                        lambda _: self._updateAutoEndpoint(endpoint_cfg['auto_format']))

            logger.debug(f'[对话框] region 字段已更新: type={region_cfg.get("type", "text")}')

        # --- 处理 endpoint 字段 ---
        endpoint_visible = endpoint_cfg.get('visible', True)
        auto_format = endpoint_cfg.get('auto_format')
        is_readonly = endpoint_cfg.get('readonly', False)
        old_endpoint = self.fieldWidgets.get('endpoint')
        endpoint_label = None
        endpoint_row = -1

        if old_endpoint:
            old_ep_value = old_endpoint.text().strip() if isinstance(old_endpoint, LineEdit) else ''
            idx = self.fieldsLayout.indexOf(old_endpoint)
            if idx >= 0:
                endpoint_row, _, _, _ = self.fieldsLayout.getItemPosition(idx)
            for lbl in self._field_labels:
                if lbl.text() == '端点:':
                    endpoint_label = lbl
                    break
        else:
            old_ep_value = ''

        if endpoint_row >= 0:
            if endpoint_visible:
                if endpoint_label:
                    endpoint_label.setVisible(True)
                old_endpoint.setParent(None)
                old_endpoint.deleteLater()

                new_endpoint = LineEdit(self)
                if auto_format:
                    # 预设服务商：显示自动生成的端点，设为只读
                    region_value = self._getCurrentRegionValue()
                    new_endpoint.setText(auto_format.format(region=region_value))
                    new_endpoint.setEnabled(False)
                else:
                    # 自定义服务商：可编辑
                    new_endpoint.setEnabled(not is_readonly)
                    placeholder = endpoint_cfg.get('placeholder', '')
                    if placeholder:
                        new_endpoint.setPlaceholderText(placeholder)
                    if old_ep_value:
                        new_endpoint.setText(old_ep_value)

                self.fieldsLayout.addWidget(new_endpoint, endpoint_row, 1)
                self.fieldWidgets['endpoint'] = new_endpoint
            else:
                # 隐藏 endpoint
                if endpoint_label:
                    endpoint_label.setVisible(False)
                old_endpoint.setVisible(False)

            logger.debug(f'[对话框] endpoint 字段: visible={endpoint_visible}, auto={auto_format}')

    def _getCurrentRegionValue(self):
        """获取当前 region 字段的值"""
        region_widget = self.fieldWidgets.get('region')
        if not region_widget:
            return ''
        if isinstance(region_widget, ComboBox):
            return region_widget.currentText()
        return region_widget.text().strip()

    def _updateAutoEndpoint(self, auto_format):
        """根据 region 值自动更新 endpoint"""
        endpoint_widget = self.fieldWidgets.get('endpoint')
        if endpoint_widget and isinstance(endpoint_widget, LineEdit):
            region_value = self._getCurrentRegionValue()
            endpoint_widget.setText(auto_format.format(region=region_value))

    def loadRemote(self, remote: Remote):
        logger.info(f'[对话框] loadRemote: name={remote.name}, type={remote.type}, '
                    f'config_keys={list(remote.config.keys())}')

        self.nameEdit.setText(remote.name)
        self.nameEdit.setEnabled(False)

        type_found = False
        for i in range(self.typeCombo.count()):
            if self.typeCombo.itemData(i) == remote.type:
                self.typeCombo.setCurrentIndex(i)
                type_found = True
                logger.debug(f'[对话框] 类型匹配: index={i}, type={remote.type}')
                break

        if not type_found:
            logger.warning(f'[对话框] 未找到匹配的类型: {remote.type}')

        loaded_fields = []
        for field_id, widget in self.fieldWidgets.items():
            if field_id in remote.config:
                if isinstance(widget, ComboBox):
                    idx = widget.findText(remote.config[field_id])
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                        loaded_fields.append(f'{field_id}={remote.config[field_id]}')
                else:
                    widget.setText(str(remote.config[field_id]))
                    loaded_fields.append(f'{field_id}=***' if 'pass' in field_id or 'secret' in field_id or 'token' in field_id
                                        else f'{field_id}={remote.config[field_id]}')

        logger.info(f'[对话框] loadRemote 完成，已加载字段: {loaded_fields}')

    def getData(self) -> tuple:
        name = self.nameEdit.text().strip()
        type_id = self.typeCombo.currentData()
        options = {}

        for field_id, widget in self.fieldWidgets.items():
            # 使用 isHidden() 而非 isVisible()：
            # QFluentWidgets Dialog.accept() 内部调用 hide() 隐藏对话框，
            # 导致 isVisible() 对所有子 widget 返回 False（因为它检查整个祖先链）。
            # isHidden() 只检查 widget 自身是否被显式隐藏，不受父级影响。
            if widget.isHidden():
                continue
            if isinstance(widget, ComboBox):
                value = widget.currentText()
            else:
                value = widget.text().strip()
            if value:
                options[field_id] = value

        # S3: 自动生成 endpoint
        if type_id == 's3' and 'provider' in options:
            s3_config = get_provider('s3') or {}
            provider_configs = s3_config.get('provider_config', {})
            pcfg = provider_configs.get(options['provider'], {})
            ep_cfg = pcfg.get('endpoint', {})
            auto_fmt = ep_cfg.get('auto_format')
            if auto_fmt and 'endpoint' not in options:
                region = options.get('region', '')
                if region:
                    options['endpoint'] = auto_fmt.format(region=region)

        safe_options = {k: ('***' if 'pass' in k or 'secret' in k or 'token' in k else v)
                       for k, v in options.items()}
        logger.info(f'[对话框] getData: name={name}, type={type_id}, options={safe_options}')

        return name, type_id, options


class RemoteInterface(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('remoteInterface')
        self.setWidgetResizable(True)

        self.rclone = RClone()
        self.configManager = ConfigManager(self.rclone)
        logger.info('[远程存储] RemoteInterface 初始化')

        self.initUI()
        self.loadRemotes()

    def initUI(self):
        self.scrollWidget = QWidget()
        self.setWidget(self.scrollWidget)
        self.enableTransparentBackground()

        self.mainLayout = QVBoxLayout(self.scrollWidget)
        self.mainLayout.setContentsMargins(36, 20, 36, 20)
        self.mainLayout.setSpacing(16)

        headerLayout = QHBoxLayout()
        self.titleLabel = TitleLabel('远程存储', self)
        self.addBtn = PrimaryPushButton(FIF.ADD, '添加', self)
        self.addBtn.clicked.connect(self.showAddDialog)
        self.refreshBtn = PushButton(FIF.SYNC, '刷新', self)
        self.refreshBtn.clicked.connect(self.loadRemotes)

        headerLayout.addWidget(self.titleLabel)
        headerLayout.addStretch()
        headerLayout.addWidget(self.refreshBtn)
        headerLayout.addWidget(self.addBtn)

        self.mainLayout.addLayout(headerLayout)

        self.listWidget = QWidget()
        self.listLayout = QVBoxLayout(self.listWidget)
        self.listLayout.setContentsMargins(0, 0, 0, 0)
        self.listLayout.setSpacing(8)

        self.mainLayout.addWidget(self.listWidget)
        self.mainLayout.addStretch()

    def loadRemotes(self):
        logger.info('[远程存储] 开始加载远程存储列表')

        count = self.listLayout.count()
        while self.listLayout.count():
            item = self.listLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        logger.debug(f'[远程存储] 已清理 {count} 个旧的列表项')

        self.configManager.refresh()
        remotes = self.configManager.list_remotes()
        logger.info(f'[远程存储] 获取到 {len(remotes)} 个远程存储配置')

        if not remotes:
            emptyLabel = CaptionLabel('暂无远程存储配置，点击"添加"创建', self)
            emptyLabel.setAlignment(Qt.AlignCenter)
            self.listLayout.addWidget(emptyLabel)
            logger.info('[远程存储] 无远程存储配置，显示空提示')
            return

        for remote in remotes:
            card = RemoteCard(remote, self)
            card.editClicked.connect(self.showEditDialog)
            card.deleteClicked.connect(self.deleteRemote)
            card.testClicked.connect(self.testRemote)
            self.listLayout.addWidget(card)
            logger.debug(f'[远程存储] 已添加卡片: {remote.name} ({remote.type})')

        logger.info(f'[远程存储] 远程存储列表加载完成，共 {len(remotes)} 项')

    def showAddDialog(self):
        logger.info('[远程存储] 用户打开添加远程存储对话框')
        existing_names = [r.name for r in self.configManager.list_remotes()]
        dialog = AddRemoteDialog(self, existing_names=existing_names)
        result = dialog.exec()
        logger.info(f'[远程存储] 添加对话框关闭，result={result} (1=OK, 0=Cancel)')

        if result:
            name, type_id, options = dialog.getData()
            if name and type_id:
                logger.info(f'[远程存储] 用户确认添加远程存储: name={name}, type={type_id}')
                success = self.configManager.add_remote(name, type_id, **options)
                if success:
                    logger.info(f'[远程存储] 远程存储添加成功: {name}')
                    InfoBar.success('成功', f'已添加远程存储: {name}',
                                   parent=self, position=InfoBarPosition.TOP)
                    self.loadRemotes()
                    signalBus.remoteAdded.emit(name)
                else:
                    logger.error(f'[远程存储] 远程存储添加失败: {name} (configManager.add_remote 返回 False)')
                    InfoBar.error('失败', '添加远程存储失败',
                                 parent=self, position=InfoBarPosition.TOP)
            else:
                logger.warning(f'[远程存储] 添加对话框数据不完整: name={name}, type_id={type_id}')

    def showEditDialog(self, name: str):
        logger.info(f'[远程存储] 用户打开编辑远程存储对话框: {name}')
        remote = self.configManager.get_remote(name)
        if not remote:
            logger.warning(f'[远程存储] 未找到远程存储配置: {name}')
            return

        logger.info(f'[远程存储] 获取到远程存储配置: {name}, type={remote.type}, '
                    f'config_keys={list(remote.config.keys())}')

        dialog = AddRemoteDialog(self, remote)
        result = dialog.exec()
        logger.info(f'[远程存储] 编辑对话框关闭，result={result} (1=OK, 0=Cancel)')

        if result:
            _, _, options = dialog.getData()
            logger.info(f'[远程存储] 用户确认编辑远程存储: {name}, options_count={len(options)}')
            success = self.configManager.update_remote(name, **options)
            if success:
                logger.info(f'[远程存储] 远程存储更新成功: {name}')
                InfoBar.success('成功', f'已更新远程存储: {name}',
                               parent=self, position=InfoBarPosition.TOP)
                self.loadRemotes()
                signalBus.remoteUpdated.emit(name)
            else:
                logger.error(f'[远程存储] 远程存储更新失败: {name} (configManager.update_remote 返回 False)')
                InfoBar.error('失败', f'更新远程存储失败: {name}',
                             parent=self, position=InfoBarPosition.TOP)

    def deleteRemote(self, name: str):
        logger.info(f'[远程存储] 用户请求删除远程存储: {name}')
        box = MessageBox('确认删除', f'确定要删除远程存储 "{name}" 吗？', self.window())
        result = box.exec()
        logger.info(f'[远程存储] 删除确认对话框结果: {result} (1=确认, 0=取消)')

        if result:
            logger.info(f'[远程存储] 用户确认删除远程存储: {name}')
            success = self.configManager.delete_remote(name)
            if success:
                logger.info(f'[远程存储] 远程存储删除成功: {name}')
                InfoBar.success('成功', f'已删除远程存储: {name}',
                               parent=self, position=InfoBarPosition.TOP)
                self.loadRemotes()
                signalBus.remoteRemoved.emit(name)
            else:
                logger.error(f'[远程存储] 远程存储删除失败: {name} (configManager.delete_remote 返回 False)')
                InfoBar.error('失败', f'删除远程存储失败: {name}',
                             parent=self, position=InfoBarPosition.TOP)
        else:
            logger.info(f'[远程存储] 用户取消删除远程存储: {name}')

    def testRemote(self, name: str):
        logger.info(f'[远程存储] 用户测试远程存储连接: {name}')
        success, message = self.configManager.test_remote(name)
        if success:
            logger.info(f'[远程存储] 远程存储连接测试成功: {name}, message={message}')
            InfoBar.success('连接成功', message,
                           parent=self, position=InfoBarPosition.TOP)
        else:
            logger.warning(f'[远程存储] 远程存储连接测试失败: {name}, message={message}')
            InfoBar.error('连接失败', message,
                         parent=self, position=InfoBarPosition.TOP)
