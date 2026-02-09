# RClone GUI

基于 PySide6 和 QFluentWidgets 的 RClone 图形界面应用，提供直观的远程存储管理、文件同步和挂载功能。

## 功能特性

### 远程存储管理
- 支持 5 种存储协议：WebDAV、SFTP、FTP、SMB/CIFS、Amazon S3（含 AWS、阿里云 OSS、Ceph、DigitalOcean、MinIO 等子服务商）
- 可插拔的 Provider 注册表架构，通过 `app/providers/` 下的模块自动发现注册，扩展新协议只需添加一个 Python 文件
- 添加、编辑、删除远程存储配置，自动生成不重复的名称
- 测试远程存储连接可用性

### 挂载管理
- 将远程存储挂载为 Windows 本地盘符（基于 rclone mount）
- 支持开机自动挂载
- 支持只读模式和 VFS 缓存模式配置（off / minimal / writes / full）
- 自定义 VFS 缓存目录（默认 / 系统临时目录 / 自定义路径）
- 系统托盘快速全部挂载/卸载
- 自动发现系统中已有的 rclone mount 进程（外部挂载识别）
- 应用重启后通过 PowerShell 进程匹配恢复卸载能力

### 文件浏览器
- 浏览远程存储文件和文件夹
- 上传/下载文件
- 新建文件夹、删除文件/文件夹
- 异步加载，操作不阻塞 UI
- 路径导航、返回上级、回到根目录

### 同步任务
- 支持 4 种同步模式：Sync、Copy、Move、Bisync
- 定时同步（Cron 表达式，依赖 croniter）
- 预设常用 Cron 规则 + 自定义表达式，实时校验并预览下次运行时间
- 带宽限制
- 排除模式（支持通配符，每行一个）
- 干运行模式（预览同步结果，不实际执行）
- 删除目标端被排除文件选项
- 实时进度解析（百分比、速度、ETA、文件数）

### 系统功能
- 单实例运行保护（QLocalServer）
- 系统托盘最小化/关闭到托盘
- 浅色/深色/跟随系统主题切换
- 开机自启（Windows 注册表）
- 配置持久化（JSON）
- 分级日志系统（RotatingFileHandler，app.log + error.log + 控制台）
- 首次启动自动从 GitHub Releases 下载 rclone
- Windows 版本检查（要求 Build 19044+）

## 技术架构

```
app/
├── common/          # 通用模块
│   ├── config.py        # 配置管理（QConfig + 线程安全懒加载 + 代理模式）
│   ├── signal_bus.py    # 全局信号总线（Qt Signal）
│   ├── logger.py        # 单例日志系统
│   └── auto_start.py    # 开机自启（Windows 注册表操作）
├── core/            # 核心业务逻辑
│   ├── rclone.py        # RClone CLI 封装（命令注入防护 + 敏感信息脱敏）
│   ├── config_manager.py # 远程存储配置 CRUD（带缓存）
│   ├── mount_manager.py  # 挂载管理（QThread Worker + 进程生命周期管理）
│   ├── sync_manager.py   # 同步任务管理（进度解析 + 调度器集成）
│   ├── scheduler.py      # Cron 定时调度器（QTimer + croniter）
│   └── bootstrap.py      # 启动引导（系统检查 + rclone 自动下载）
├── models/          # 数据模型（dataclass）
│   ├── remote.py        # 远程存储模型
│   ├── mount.py         # 挂载配置模型（含状态机）
│   └── sync_task.py     # 同步任务模型
├── providers/       # 存储协议提供商（自动发现注册表）
│   ├── __init__.py      # Provider Registry（pkgutil 自动扫描）
│   ├── webdav.py        # WebDAV（含 123Pan、阿里云盘预设）
│   ├── sftp.py / ftp.py / smb.py / s3.py
│   └── ...              # 新增协议只需添加含 PROVIDER 字典的 .py 文件
└── views/           # UI 视图（QFluentWidgets）
    ├── main_window.py       # 主窗口（FluentWindow + 导航）
    ├── home_interface.py    # 仪表盘（统计卡片 + 快捷操作）
    ├── remote_interface.py  # 远程存储管理（动态表单 + S3/WebDAV 联动）
    ├── mount_interface.py   # 挂载管理（异步卸载 + 发现挂载）
    ├── browser_interface.py # 文件浏览器（异步加载 + 路径安全校验）
    ├── sync_interface.py    # 同步任务（Cron 预设 + 实时校验）
    └── settings_interface.py # 设置（主题/自启/缓存/RClone 路径）
```

## 环境要求

- Windows 10 21H2 (Build 19044) 及以上
- Python 3.12
- RClone（首次启动自动下载，或手动放置于 `environments/` 目录）

## 快速启动

```bash
git clone https://github.com/GamblerIX/RCloneGUI.git
cd RCloneGUI
pip install -r requirements.txt
python main.py
```

首次启动时，应用会自动检测系统架构并从 GitHub 下载对应的 rclone 可执行文件。

## 使用指南

### 首次使用

1. 启动应用后，进入"远程存储"页面
2. 点击"添加"，选择存储类型并配置连接信息（名称自动生成）
3. 配置完成后点击"测试"验证连接
4. 在"挂载管理"页面将远程存储挂载为本地盘符
5. 或使用"文件浏览器"直接浏览远程文件

### 创建同步任务

1. 进入"同步任务"页面，点击"添加"
2. 设置源路径和目标路径（支持本地路径或 `remote:path` 格式）
3. 选择同步模式：
   - **Sync**: 使目标与源完全相同（会删除目标多余文件）
   - **Copy**: 从源复制文件到目标（不删除）
   - **Move**: 从源移动文件到目标
   - **Bisync**: 双向同步
4. 可选：开启定时同步，选择预设规则或输入自定义 Cron 表达式
5. 可选：设置带宽限制、排除模式、干运行等高级选项
6. 点击"运行"立即执行，或等待定时触发

### Cron 表达式示例

| 表达式 | 说明 |
|--------|------|
| `0 2 * * *` | 每天凌晨 2 点 |
| `0 */6 * * *` | 每 6 小时一次 |
| `0 0 * * 0` | 每周日午夜 |
| `0 0 1 * *` | 每月 1 号 |

## 测试

```bash
pip install pytest pytest-cov pytest-mock pytest-qt
python -m pytest
```

项目包含 778 个测试用例，覆盖率 93%。

## CI/CD

- **CI**: 每次 push/PR 自动运行测试（GitHub Actions，Windows 环境）
- **CD**: 手动触发发布流程，支持 Nuitka / PyInstaller 双打包 + Inno Setup 安装包生成 + GitHub Release 自动发布

## 扩展存储协议

在 `app/providers/` 下新建 Python 文件，定义 `PROVIDER` 字典即可自动注册：

```python
PROVIDER = {
    'type_id': 'myprotocol',
    'name': '我的协议',
    'fields': {
        'host': {'label': '主机地址', 'required': True, 'type': 'text'},
        'user': {'label': '用户名', 'required': False, 'type': 'text'},
        'pass': {'label': '密码', 'required': False, 'type': 'password'},
    },
}
```

## 许可证

本项目采用 [AGPL v3](LICENSE) 许可证开源。

## 致谢

- [RClone](https://rclone.org/) - 强大的云存储命令行工具
- [PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) - Fluent Design 风格的 Qt 组件库
