# RClone GUI

基于 PySide6 和 QFluentWidgets 的 RClone 图形界面应用，提供直观的远程存储管理、文件同步和挂载功能。

## 功能特性

### 远程存储管理
- 支持 5 种存储协议：WebDAV、SFTP、FTP、SMB/CIFS、S3存储
- 测试远程存储连接可用性
- 内置的文件浏览器
- 支持同步任务
- 预设常用云厂商：
  - 123云盘
  - 阿里云盘

> 后续将跟进`OAuth`授权的开发。（比如：OneDrive；Google Drive）

### 挂载管理
- 将远程存储挂载为 Windows 本地盘符
- 支持开机自动挂载以持久化挂载
- 支持只读模式和 VFS 缓存模式配置
- 自动识别历史挂载（外部挂载）

## 环境要求

- Windows 10 21H2 (Build 19044) 及以上
- Python 3.12
- RClone（首次启动会自动下载至 `environments/` 目录）

## 从源码运行

```bash
git clone https://github.com/GamblerIX/RCloneGUI.git
cd RCloneGUI
pip install -r requirements.txt
python main.py
```

## 许可证

本项目采用 [AGPL v3](LICENSE) 许可证开源。

## 致谢

- [RClone](https://rclone.org/) - 强大的云存储命令行工具
- [PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) - Fluent Design 风格的 Qt 组件库
