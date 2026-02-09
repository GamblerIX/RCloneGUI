
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.models.sync_task import SyncTask, SyncMode, SyncStatus
from app.models.mount import Mount, MountStatus
from app.models.remote import Remote


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _mock_view_deps(mocker):
    mock_rclone = MagicMock()
    mock_rclone.version.return_value = "rclone v1.0.0"
    mock_rclone.rclone_path = "/usr/bin/rclone"
    mock_rclone.config_path = "/tmp/rclone.conf"
    mock_rclone.config_dump.return_value = {}
    mock_rclone.listremotes.return_value = []
    for mod in [
        "app.views.sync_interface.RClone",
        "app.views.mount_interface.RClone",
    ]:
        mocker.patch(mod, return_value=mock_rclone)

    mock_cm = MagicMock()
    mock_cm.list_remotes.return_value = []
    for mod in [
        "app.views.sync_interface.ConfigManager",
        "app.views.mount_interface.ConfigManager",
    ]:
        mocker.patch(mod, return_value=mock_cm)

    mock_mm = MagicMock()
    mock_mm.mounts = {}
    mock_mm.load_mounts.return_value = None
    mocker.patch("app.views.mount_interface.MountManager", return_value=mock_mm)

    mock_sm = MagicMock()
    mock_sm.tasks = {}
    mock_sm.load_tasks.return_value = True
    mocker.patch("app.views.sync_interface.SyncManager", return_value=mock_sm)

    return {
        "rclone": mock_rclone,
        "config_manager": mock_cm,
        "mount_manager": mock_mm,
        "sync_manager": mock_sm,
    }


def _make_task(**overrides):
    defaults = dict(
        id="task-001",
        name="测试任务",
        source="/tmp/src",
        destination="myremote:backup",
        mode=SyncMode.SYNC,
        status=SyncStatus.IDLE,
    )
    defaults.update(overrides)
    return SyncTask(**defaults)


def _make_mount(**overrides):
    defaults = dict(
        remote_name="myremote",
        remote_path="",
        drive_letter="Z",
        status=MountStatus.UNMOUNTED,
        auto_mount=False,
        read_only=False,
        cache_mode="off",
    )
    defaults.update(overrides)
    return Mount(**defaults)


def _make_remote(name="myremote", rtype="webdav"):
    return Remote(name=name, type=rtype, config={})


class TestSyncTaskCard:

    def test_init_idle_task(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task()
        card = SyncTaskCard(task)
        assert card.nameLabel.text() == "测试任务"
        assert "同步" in card.infoLabel.text()
        assert card.statusLabel.text() == "空闲"
        assert card.actionBtn.text() == "运行"
        assert not card.progressBar.isVisible()

    def test_init_running_task(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(status=SyncStatus.RUNNING)
        card = SyncTaskCard(task)
        assert card.statusLabel.text() == "运行中"
        assert card.actionBtn.text() == "停止"
        assert not card.progressBar.isHidden()

    def test_init_copy_mode_text(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(mode=SyncMode.COPY)
        card = SyncTaskCard(task)
        assert "复制" in card.infoLabel.text()

    def test_init_move_mode_text(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(mode=SyncMode.MOVE)
        card = SyncTaskCard(task)
        assert "移动" in card.infoLabel.text()

    def test_init_bisync_mode_text(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(mode=SyncMode.BISYNC)
        card = SyncTaskCard(task)
        assert "双向同步" in card.infoLabel.text()

    def test_init_fallback_name(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(name="")
        card = SyncTaskCard(task)
        assert task.id in card.nameLabel.text()

    def test_update_progress(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task()
        card = SyncTaskCard(task)
        assert card.progressBar.isHidden()
        card.updateProgress(50)
        assert card.progressBar.value() == 50
        assert not card.progressBar.isHidden()

    def test_update_status_to_running(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task()
        card = SyncTaskCard(task)
        card.updateStatus(SyncStatus.RUNNING)
        assert card.statusLabel.text() == "运行中"
        assert not card.progressBar.isHidden()
        assert card.actionBtn.text() == "停止"

    def test_update_status_to_completed(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(status=SyncStatus.RUNNING)
        card = SyncTaskCard(task)
        card.updateStatus(SyncStatus.COMPLETED)
        assert card.statusLabel.text() == "已完成"
        assert card.progressBar.isHidden()
        assert card.actionBtn.text() == "运行"

    def test_update_status_to_error(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task()
        card = SyncTaskCard(task)
        card.updateStatus(SyncStatus.ERROR)
        assert card.statusLabel.text() == "错误"
        assert card.actionBtn.text() == "运行"

    def test_update_status_to_paused(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task()
        card = SyncTaskCard(task)
        card.updateStatus(SyncStatus.PAUSED)
        assert card.statusLabel.text() == "已暂停"

    def test_edit_signal(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task()
        card = SyncTaskCard(task)
        received = []
        card.editClicked.connect(received.append)
        card.editBtn.click()
        assert received == [task.id]

    def test_delete_signal(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task()
        card = SyncTaskCard(task)
        received = []
        card.deleteClicked.connect(received.append)
        card.deleteBtn.click()
        assert received == [task.id]

    def test_run_signal_when_idle(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(status=SyncStatus.IDLE)
        card = SyncTaskCard(task)
        received = []
        card.runClicked.connect(received.append)
        card.actionBtn.click()
        assert received == [task.id]

    def test_stop_signal_when_running(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(status=SyncStatus.RUNNING)
        card = SyncTaskCard(task)
        received = []
        card.stopClicked.connect(received.append)
        card.actionBtn.click()
        assert received == [task.id]

    def test_update_button_toggles_correctly(self):
        from app.views.sync_interface import SyncTaskCard
        task = _make_task(status=SyncStatus.IDLE)
        card = SyncTaskCard(task)
        run_received = []
        stop_received = []
        card.runClicked.connect(run_received.append)
        card.stopClicked.connect(stop_received.append)

        card.updateStatus(SyncStatus.RUNNING)
        card.actionBtn.click()
        assert len(stop_received) == 1
        assert len(run_received) == 0

        card.updateStatus(SyncStatus.IDLE)
        card.actionBtn.click()
        assert len(run_received) == 1


class TestAddSyncDialog:

    def test_init_add_mode(self):
        from app.views.sync_interface import AddSyncDialog
        remotes = [_make_remote("r1"), _make_remote("r2", "sftp")]
        dlg = AddSyncDialog(remotes, None)
        assert dlg.nameEdit.text() == ""
        assert dlg.sourceEdit.text() == ""
        assert dlg.destEdit.text() == ""
        assert not dlg.scheduleSwitch.isChecked()
        assert not dlg.dryRunSwitch.isChecked()
        assert not dlg.deleteExcludedSwitch.isChecked()

    def test_init_edit_mode_loads_task(self):
        from app.views.sync_interface import AddSyncDialog
        task = _make_task(
            name="编辑任务",
            source="/src",
            destination="remote:dst",
            mode=SyncMode.COPY,
            scheduled=True,
            cron_expression="0 2 * * *",
            bandwidth_limit="10M",
            exclude_patterns=["*.tmp", "*.log"],
            dry_run=True,
            delete_excluded=True,
        )
        remotes = [_make_remote("remote")]
        dlg = AddSyncDialog(remotes, None, task)
        assert dlg.nameEdit.text() == "编辑任务"
        assert dlg.sourceEdit.text() == "/src"
        assert dlg.destEdit.text() == "remote:dst"
        assert dlg.scheduleSwitch.isChecked()
        assert dlg.cronEdit.text() == "0 2 * * *"
        assert dlg.bwLimitEdit.text() == "10M"
        assert "*.tmp" in dlg.excludeEdit.toPlainText()
        assert "*.log" in dlg.excludeEdit.toPlainText()
        assert dlg.dryRunSwitch.isChecked()
        assert dlg.deleteExcludedSwitch.isChecked()

    def test_get_data_returns_correct_dict(self):
        from app.views.sync_interface import AddSyncDialog
        dlg = AddSyncDialog([], None)
        dlg.nameEdit.setText("任务A")
        dlg.sourceEdit.setText("/a")
        dlg.destEdit.setText("/b")
        dlg.bwLimitEdit.setText("5M")
        dlg.excludeEdit.setPlainText("*.bak\n*.tmp")
        dlg.dryRunSwitch.setChecked(True)
        dlg.deleteExcludedSwitch.setChecked(True)
        data = dlg.getData()
        assert data["name"] == "任务A"
        assert data["source"] == "/a"
        assert data["destination"] == "/b"
        assert data["mode"] == SyncMode.SYNC
        assert data["bandwidth_limit"] == "5M"
        assert data["exclude_patterns"] == ["*.bak", "*.tmp"]
        assert data["dry_run"] is True
        assert data["delete_excluded"] is True
        assert data["scheduled"] is False
        assert data["cron_expression"] == ""

    def test_get_data_with_schedule(self):
        from app.views.sync_interface import AddSyncDialog
        dlg = AddSyncDialog([], None)
        dlg.scheduleSwitch.setChecked(True)
        dlg.onScheduleToggled(True)
        dlg.cronEdit.setText("0 3 * * *")
        data = dlg.getData()
        assert data["scheduled"] is True
        assert data["cron_expression"] == "0 3 * * *"

    def test_browse_local_sets_text(self, mocker):
        from app.views.sync_interface import AddSyncDialog
        mocker.patch(
            "app.views.sync_interface.QFileDialog.getExistingDirectory",
            return_value="/selected/path",
        )
        dlg = AddSyncDialog([], None)
        dlg.browseLocal(dlg.sourceEdit)
        assert dlg.sourceEdit.text() == "/selected/path"

    def test_browse_local_empty_does_nothing(self, mocker):
        from app.views.sync_interface import AddSyncDialog
        mocker.patch(
            "app.views.sync_interface.QFileDialog.getExistingDirectory",
            return_value="",
        )
        dlg = AddSyncDialog([], None)
        dlg.sourceEdit.setText("original")
        dlg.browseLocal(dlg.sourceEdit)
        assert dlg.sourceEdit.text() == "original"

    def test_apply_remote_to_source(self):
        from app.views.sync_interface import AddSyncDialog
        remotes = [_make_remote("cloud")]
        dlg = AddSyncDialog(remotes, None)
        dlg.remoteCombo.setCurrentIndex(1)
        dlg.applyRemote(dlg.sourceEdit)
        assert dlg.sourceEdit.text() == "cloud:"

    def test_apply_remote_index_zero_does_nothing(self):
        from app.views.sync_interface import AddSyncDialog
        remotes = [_make_remote("cloud")]
        dlg = AddSyncDialog(remotes, None)
        dlg.remoteCombo.setCurrentIndex(0)
        dlg.sourceEdit.setText("keep")
        dlg.applyRemote(dlg.sourceEdit)
        assert dlg.sourceEdit.text() == "keep"

    def test_on_schedule_toggled_enable(self):
        from app.views.sync_interface import AddSyncDialog
        dlg = AddSyncDialog([], None)
        dlg.onScheduleToggled(True)
        assert dlg.schedulePresetCombo.isEnabled()
        assert dlg.cronEdit.isEnabled()
        assert dlg.nextRunLabel.isEnabled()

    def test_on_schedule_toggled_disable(self):
        from app.views.sync_interface import AddSyncDialog
        dlg = AddSyncDialog([], None)
        dlg.onScheduleToggled(True)
        dlg.cronEdit.setText("0 2 * * *")
        dlg.onScheduleToggled(False)
        assert not dlg.schedulePresetCombo.isEnabled()
        assert not dlg.cronEdit.isEnabled()
        assert dlg.cronEdit.text() == ""
        assert dlg.nextRunLabel.text() == "下次运行: -"

    def test_on_preset_changed_sets_cron(self):
        from app.views.sync_interface import AddSyncDialog
        dlg = AddSyncDialog([], None)
        dlg.onScheduleToggled(True)
        dlg.schedulePresetCombo.setCurrentIndex(1)
        assert dlg.cronEdit.text() == ""

    def test_on_preset_changed_manual_call(self):
        from app.views.sync_interface import AddSyncDialog
        dlg = AddSyncDialog([], None)
        dlg.onScheduleToggled(True)
        dlg.cronEdit.setText("0 2 * * *")
        assert dlg.cronEdit.text() == "0 2 * * *"

    def test_validate_cron_empty(self):
        from app.views.sync_interface import AddSyncDialog
        dlg = AddSyncDialog([], None)
        dlg.validateCron("")
        assert dlg.cronStatusLabel.text() == ""
        assert dlg.nextRunLabel.text() == "下次运行: -"

    def test_validate_cron_valid(self, mocker):
        from app.views.sync_interface import AddSyncDialog
        mocker.patch("app.views.sync_interface.CRONITER_AVAILABLE", True)
        mock_croniter = mocker.patch("app.views.sync_interface.croniter")
        from datetime import datetime
        mock_instance = MagicMock()
        mock_instance.get_next.return_value = datetime(2025, 1, 1, 2, 0)
        mock_croniter.return_value = mock_instance
        dlg = AddSyncDialog([], None)
        dlg.validateCron("0 2 * * *")
        assert "有效" in dlg.cronStatusLabel.text()

    def test_validate_cron_invalid(self, mocker):
        from app.views.sync_interface import AddSyncDialog
        mocker.patch("app.views.sync_interface.CRONITER_AVAILABLE", True)
        mock_croniter = mocker.patch("app.views.sync_interface.croniter")
        mock_croniter.side_effect = ValueError("bad cron")
        dlg = AddSyncDialog([], None)
        dlg.validateCron("invalid")
        assert "无效" in dlg.cronStatusLabel.text()

    def test_validate_cron_no_croniter(self, mocker):
        from app.views.sync_interface import AddSyncDialog
        mocker.patch("app.views.sync_interface.CRONITER_AVAILABLE", False)
        dlg = AddSyncDialog([], None)
        dlg.validateCron("0 2 * * *")
        assert "croniter" in dlg.cronStatusLabel.text()

    def test_load_task_sets_mode_combo(self):
        from app.views.sync_interface import AddSyncDialog
        task = _make_task(mode=SyncMode.MOVE)
        dlg = AddSyncDialog([], None)
        dlg.loadTask(task)
        assert dlg.modeCombo.currentIndex() == 0

    def test_get_data_exclude_empty_lines(self):
        from app.views.sync_interface import AddSyncDialog
        dlg = AddSyncDialog([], None)
        dlg.excludeEdit.setPlainText("*.tmp\n\n*.log\n  \n")
        data = dlg.getData()
        assert data["exclude_patterns"] == ["*.tmp", "*.log"]


class TestSyncInterface:

    @pytest.fixture
    def deps(self, mocker):
        return _mock_view_deps(mocker)

    @pytest.fixture
    def iface(self, deps):
        from app.views.sync_interface import SyncInterface
        return SyncInterface()

    def test_instantiation(self, iface):
        assert iface.objectName() == "syncInterface"

    def test_load_tasks_empty(self, iface):
        iface.syncManager.tasks = {}
        iface.loadTasks()
        assert iface.listLayout.count() == 1
        assert len(iface.taskCards) == 0

    def test_load_tasks_with_tasks(self, iface):
        t1 = _make_task(id="t1", name="任务1")
        t2 = _make_task(id="t2", name="任务2")
        iface.syncManager.tasks = {"t1": t1, "t2": t2}
        iface.loadTasks()
        assert len(iface.taskCards) == 2
        assert "t1" in iface.taskCards
        assert "t2" in iface.taskCards

    def test_load_tasks_clears_previous(self, iface):
        t1 = _make_task(id="t1", name="任务1")
        iface.syncManager.tasks = {"t1": t1}
        iface.loadTasks()
        assert len(iface.taskCards) == 1
        iface.syncManager.tasks = {}
        iface.loadTasks()
        assert len(iface.taskCards) == 0

    def test_show_add_dialog_confirm(self, iface, mocker):
        mock_dialog_cls = mocker.patch("app.views.sync_interface.AddSyncDialog")
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = True
        mock_dlg.getData.return_value = {
            "name": "新任务",
            "source": "/src",
            "destination": "/dst",
            "mode": SyncMode.SYNC,
            "scheduled": False,
            "cron_expression": "",
            "bandwidth_limit": "",
            "exclude_patterns": [],
            "dry_run": False,
            "delete_excluded": False,
        }
        mock_dialog_cls.return_value = mock_dlg
        mock_infobar = mocker.patch("app.views.sync_interface.InfoBar")

        iface.showAddDialog()

        iface.syncManager.add_task.assert_called_once()
        mock_infobar.success.assert_called_once()

    def test_show_add_dialog_cancel(self, iface, mocker):
        mock_dialog_cls = mocker.patch("app.views.sync_interface.AddSyncDialog")
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = False
        mock_dialog_cls.return_value = mock_dlg

        iface.showAddDialog()

        iface.syncManager.add_task.assert_not_called()

    def test_show_add_dialog_empty_source(self, iface, mocker):
        mock_dialog_cls = mocker.patch("app.views.sync_interface.AddSyncDialog")
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = True
        mock_dlg.getData.return_value = {
            "name": "x", "source": "", "destination": "/dst",
            "mode": SyncMode.SYNC, "scheduled": False, "cron_expression": "",
            "bandwidth_limit": "", "exclude_patterns": [], "dry_run": False,
            "delete_excluded": False,
        }
        mock_dialog_cls.return_value = mock_dlg

        iface.showAddDialog()
        iface.syncManager.add_task.assert_not_called()

    def test_show_add_dialog_with_schedule(self, iface, mocker):
        mock_dialog_cls = mocker.patch("app.views.sync_interface.AddSyncDialog")
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = True
        mock_dlg.getData.return_value = {
            "name": "定时", "source": "/s", "destination": "/d",
            "mode": SyncMode.SYNC, "scheduled": True, "cron_expression": "0 2 * * *",
            "bandwidth_limit": "", "exclude_patterns": [], "dry_run": False,
            "delete_excluded": False,
        }
        mock_dialog_cls.return_value = mock_dlg
        mock_task = MagicMock()
        mock_task.id = "new-id"
        iface.syncManager.add_task.return_value = mock_task
        iface.syncManager.enable_schedule.return_value = True
        mocker.patch("app.views.sync_interface.InfoBar")

        iface.showAddDialog()
        iface.syncManager.enable_schedule.assert_called_once_with("new-id", "0 2 * * *")

    def test_show_edit_dialog_confirm(self, iface, mocker):
        task = _make_task(id="e1", name="旧名")
        iface.syncManager.tasks = {"e1": task}

        mock_dialog_cls = mocker.patch("app.views.sync_interface.AddSyncDialog")
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = True
        mock_dlg.getData.return_value = {
            "name": "新名", "source": "/new_src", "destination": "/new_dst",
            "mode": SyncMode.COPY, "scheduled": False, "cron_expression": "",
            "bandwidth_limit": "5M", "exclude_patterns": ["*.bak"],
            "dry_run": True, "delete_excluded": True,
        }
        mock_dialog_cls.return_value = mock_dlg

        iface.showEditDialog("e1")

        assert task.name == "新名"
        assert task.source == "/new_src"
        assert task.destination == "/new_dst"
        assert task.mode == SyncMode.COPY
        assert task.bandwidth_limit == "5M"
        assert task.exclude_patterns == ["*.bak"]
        assert task.dry_run is True
        assert task.delete_excluded is True
        iface.syncManager.save_tasks.assert_called()

    def test_show_edit_dialog_nonexistent_task(self, iface, mocker):
        iface.syncManager.tasks = {}
        mock_dialog_cls = mocker.patch("app.views.sync_interface.AddSyncDialog")
        iface.showEditDialog("nonexistent")
        mock_dialog_cls.assert_not_called()

    def test_delete_task_confirm(self, iface, mocker):
        mock_box_cls = mocker.patch("app.views.sync_interface.MessageBox")
        mock_box = MagicMock()
        mock_box.exec.return_value = True
        mock_box_cls.return_value = mock_box

        iface.deleteTask("d1")
        iface.syncManager.remove_task.assert_called_once_with("d1")

    def test_delete_task_cancel(self, iface, mocker):
        mock_box_cls = mocker.patch("app.views.sync_interface.MessageBox")
        mock_box = MagicMock()
        mock_box.exec.return_value = False
        mock_box_cls.return_value = mock_box

        iface.deleteTask("d1")
        iface.syncManager.remove_task.assert_not_called()

    def test_run_task(self, iface):
        iface.runTask("r1")
        iface.syncManager.run_task.assert_called_once_with("r1")

    def test_stop_task(self, iface):
        iface.stopTask("s1")
        iface.syncManager.cancel_task.assert_called_once_with("s1")

    def test_on_task_status_changed(self, iface):
        task = _make_task(id="sc1")
        iface.syncManager.tasks = {"sc1": task}
        iface.loadTasks()
        iface.onTaskStatusChanged("sc1", SyncStatus.RUNNING)
        assert iface.taskCards["sc1"].statusLabel.text() == "运行中"

    def test_on_task_status_changed_unknown_id(self, iface):
        iface.onTaskStatusChanged("unknown", SyncStatus.RUNNING)

    def test_on_task_progress(self, iface):
        task = _make_task(id="p1")
        iface.syncManager.tasks = {"p1": task}
        iface.loadTasks()
        iface.onTaskProgress("p1", 75)
        assert iface.taskCards["p1"].progressBar.value() == 75

    def test_on_task_progress_unknown_id(self, iface):
        iface.onTaskProgress("unknown", 50)

    def test_on_task_error(self, iface, mocker):
        mock_infobar = mocker.patch("app.views.sync_interface.InfoBar")
        iface.onTaskError("err1", "连接失败")
        mock_infobar.error.assert_called_once()


class TestMountCard:

    def test_init_unmounted(self):
        from app.views.mount_interface import MountCard
        mount = _make_mount()
        card = MountCard(mount)
        assert "myremote" in card.nameLabel.text()
        assert "Z" in card.nameLabel.text()
        assert card.statusLabel.text() == "未挂载"
        assert card.actionBtn.text() == "挂载"

    def test_init_mounted(self, mocker):
        from app.views.mount_interface import MountCard
        mount = _make_mount(status=MountStatus.MOUNTED)
        mocker.patch.object(type(mount), "is_mounted", new_callable=lambda: property(lambda self: self.status == MountStatus.MOUNTED))
        card = MountCard(mount)
        assert card.statusLabel.text() == "已挂载"
        assert card.actionBtn.text() == "卸载"

    def test_init_mounting(self):
        from app.views.mount_interface import MountCard
        mount = _make_mount(status=MountStatus.MOUNTING)
        card = MountCard(mount)
        assert card.statusLabel.text() == "挂载中..."

    def test_init_error(self):
        from app.views.mount_interface import MountCard
        mount = _make_mount(status=MountStatus.ERROR)
        card = MountCard(mount)
        assert card.statusLabel.text() == "错误"

    def test_update_status_to_mounted(self, mocker):
        from app.views.mount_interface import MountCard
        mount = _make_mount()
        mocker.patch.object(type(mount), "is_mounted", new_callable=lambda: property(lambda self: self.status == MountStatus.MOUNTED))
        card = MountCard(mount)
        card.updateStatus(MountStatus.MOUNTED)
        assert card.statusLabel.text() == "已挂载"
        assert card.actionBtn.text() == "卸载"

    def test_update_status_to_unmounted(self, mocker):
        from app.views.mount_interface import MountCard
        mount = _make_mount(status=MountStatus.MOUNTED)
        mocker.patch.object(type(mount), "is_mounted", new_callable=lambda: property(lambda self: self.status == MountStatus.MOUNTED))
        card = MountCard(mount)
        card.updateStatus(MountStatus.UNMOUNTED)
        assert card.statusLabel.text() == "未挂载"
        assert card.actionBtn.text() == "挂载"

    def test_edit_signal(self):
        from app.views.mount_interface import MountCard
        mount = _make_mount()
        card = MountCard(mount)
        received = []
        card.editClicked.connect(received.append)
        card.editBtn.click()
        assert received == ["myremote"]

    def test_delete_signal(self):
        from app.views.mount_interface import MountCard
        mount = _make_mount()
        card = MountCard(mount)
        received = []
        card.deleteClicked.connect(received.append)
        card.deleteBtn.click()
        assert received == ["myremote"]

    def test_mount_signal_when_unmounted(self):
        from app.views.mount_interface import MountCard
        mount = _make_mount(status=MountStatus.UNMOUNTED)
        card = MountCard(mount)
        received = []
        card.mountClicked.connect(received.append)
        card.actionBtn.click()
        assert received == ["myremote"]

    def test_unmount_signal_when_mounted(self, mocker):
        from app.views.mount_interface import MountCard
        mount = _make_mount(status=MountStatus.MOUNTED)
        mocker.patch.object(type(mount), "is_mounted", new_callable=lambda: property(lambda self: self.status == MountStatus.MOUNTED))
        card = MountCard(mount)
        received = []
        card.unmountClicked.connect(received.append)
        card.actionBtn.click()
        assert received == ["myremote"]

    def test_update_button_toggles(self, mocker):
        from app.views.mount_interface import MountCard
        mount = _make_mount(status=MountStatus.UNMOUNTED)
        mocker.patch.object(type(mount), "is_mounted", new_callable=lambda: property(lambda self: self.status == MountStatus.MOUNTED))
        card = MountCard(mount)
        mount_received = []
        unmount_received = []
        card.mountClicked.connect(mount_received.append)
        card.unmountClicked.connect(unmount_received.append)

        card.updateStatus(MountStatus.MOUNTED)
        card.actionBtn.click()
        assert len(unmount_received) == 1
        assert len(mount_received) == 0

        card.updateStatus(MountStatus.UNMOUNTED)
        card.actionBtn.click()
        assert len(mount_received) == 1


class TestAddMountDialog:

    def test_init_add_mode(self):
        from app.views.mount_interface import AddMountDialog
        remotes = [_make_remote("r1"), _make_remote("r2", "sftp")]
        dlg = AddMountDialog(remotes, ["X", "Y", "Z"], None)
        assert dlg.remoteCombo.count() == 2
        assert dlg.driveCombo.count() == 3
        assert not dlg.autoSwitch.isChecked()
        assert not dlg.roSwitch.isChecked()

    def test_init_edit_mode_loads_mount(self, mocker):
        from app.views.mount_interface import AddMountDialog
        mount = _make_mount(
            remote_name="cloud",
            drive_letter="X",
            cache_mode="full",
            auto_mount=True,
            read_only=True,
        )
        remotes = [_make_remote("cloud")]
        dlg = AddMountDialog(remotes, ["X", "Y"], None, mount)
        assert dlg.remoteCombo.currentText() == "cloud"
        assert not dlg.remoteCombo.isEnabled()
        assert "X" in dlg.driveCombo.currentText()
        assert dlg.cacheCombo.currentText() == "full"
        assert dlg.autoSwitch.isChecked()
        assert dlg.roSwitch.isChecked()

    def test_get_data_returns_correct_dict(self):
        from app.views.mount_interface import AddMountDialog
        remotes = [_make_remote("nas")]
        dlg = AddMountDialog(remotes, ["Z"], None)
        dlg.remoteCombo.setCurrentIndex(0)
        dlg.driveCombo.setCurrentIndex(0)
        dlg.cacheCombo.setCurrentIndex(2)
        dlg.autoSwitch.setChecked(True)
        dlg.roSwitch.setChecked(True)
        data = dlg.getData()
        assert data["remote_name"] == "nas"
        assert data["drive_letter"] == "Z"
        assert data["cache_mode"] == "writes"
        assert data["auto_mount"] is True
        assert data["read_only"] is True

    def test_load_mount_adds_missing_drive(self):
        from app.views.mount_interface import AddMountDialog
        mount = _make_mount(remote_name="test", drive_letter="W")
        remotes = [_make_remote("test")]
        dlg = AddMountDialog(remotes, ["X", "Y"], None, mount)
        found = False
        for i in range(dlg.driveCombo.count()):
            if "W" in dlg.driveCombo.itemText(i):
                found = True
                break
        assert found

    def test_load_mount_cache_mode_selection(self):
        from app.views.mount_interface import AddMountDialog
        mount = _make_mount(cache_mode="minimal")
        remotes = [_make_remote("myremote")]
        dlg = AddMountDialog(remotes, ["Z"], None, mount)
        assert dlg.cacheCombo.currentText() == "minimal"


class TestMountInterface:

    @pytest.fixture
    def deps(self, mocker):
        return _mock_view_deps(mocker)

    @pytest.fixture
    def iface(self, deps):
        from app.views.mount_interface import MountInterface
        return MountInterface()

    def test_instantiation(self, iface):
        assert iface.objectName() == "mountInterface"

    def test_load_mounts_empty(self, iface):
        iface.mountManager.mounts = {}
        iface.loadMounts()
        assert iface.listLayout.count() == 1
        assert len(iface.mountCards) == 0

    def test_load_mounts_with_mounts(self, iface):
        m1 = _make_mount(remote_name="r1", drive_letter="X")
        m2 = _make_mount(remote_name="r2", drive_letter="Y")
        iface.mountManager.mounts = {"r1": m1, "r2": m2}
        iface.loadMounts()
        assert len(iface.mountCards) == 2
        assert "r1" in iface.mountCards
        assert "r2" in iface.mountCards

    def test_load_mounts_clears_previous(self, iface):
        m1 = _make_mount(remote_name="r1", drive_letter="X")
        iface.mountManager.mounts = {"r1": m1}
        iface.loadMounts()
        assert len(iface.mountCards) == 1
        iface.mountManager.mounts = {}
        iface.loadMounts()
        assert len(iface.mountCards) == 0

    def test_show_add_dialog_confirm(self, iface, mocker):
        iface.configManager.list_remotes.return_value = [_make_remote("nas")]
        iface.mountManager.get_available_drives.return_value = ["Z"]

        mock_dialog_cls = mocker.patch("app.views.mount_interface.AddMountDialog")
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = True
        mock_dlg.getData.return_value = {
            "remote_name": "nas",
            "drive_letter": "Z",
            "cache_mode": "off",
            "auto_mount": False,
            "read_only": False,
        }
        mock_dialog_cls.return_value = mock_dlg
        mock_infobar = mocker.patch("app.views.mount_interface.InfoBar")

        iface.showAddDialog()

        iface.mountManager.add_mount.assert_called_once()
        mock_infobar.success.assert_called_once()

    def test_show_add_dialog_cancel(self, iface, mocker):
        iface.configManager.list_remotes.return_value = [_make_remote("nas")]
        iface.mountManager.get_available_drives.return_value = ["Z"]

        mock_dialog_cls = mocker.patch("app.views.mount_interface.AddMountDialog")
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = False
        mock_dialog_cls.return_value = mock_dlg

        iface.showAddDialog()
        iface.mountManager.add_mount.assert_not_called()

    def test_show_add_dialog_no_remotes(self, iface, mocker):
        iface.configManager.list_remotes.return_value = []
        mock_infobar = mocker.patch("app.views.mount_interface.InfoBar")

        iface.showAddDialog()
        mock_infobar.warning.assert_called_once()

    def test_show_add_dialog_no_drives(self, iface, mocker):
        iface.configManager.list_remotes.return_value = [_make_remote("nas")]
        iface.mountManager.get_available_drives.return_value = []
        mock_infobar = mocker.patch("app.views.mount_interface.InfoBar")

        iface.showAddDialog()
        mock_infobar.error.assert_called_once()

    def test_show_edit_dialog_confirm(self, iface, mocker):
        mount = _make_mount(remote_name="ed", drive_letter="X")
        iface.mountManager.mounts = {"ed": mount}
        iface.configManager.list_remotes.return_value = [_make_remote("ed")]
        iface.mountManager.get_available_drives.return_value = ["X", "Y"]

        mock_dialog_cls = mocker.patch("app.views.mount_interface.AddMountDialog")
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = True
        mock_dlg.getData.return_value = {
            "remote_name": "ed",
            "drive_letter": "Y",
            "cache_mode": "full",
            "auto_mount": True,
            "read_only": True,
        }
        mock_dialog_cls.return_value = mock_dlg

        iface.showEditDialog("ed")

        assert mount.drive_letter == "Y"
        assert mount.cache_mode == "full"
        assert mount.auto_mount is True
        assert mount.read_only is True
        iface.mountManager.save_mounts.assert_called()

    def test_show_edit_dialog_nonexistent(self, iface, mocker):
        iface.mountManager.mounts = {}
        mock_dialog_cls = mocker.patch("app.views.mount_interface.AddMountDialog")
        iface.showEditDialog("nonexistent")
        mock_dialog_cls.assert_not_called()

    def test_delete_mount_confirm(self, iface, mocker):
        mock_box_cls = mocker.patch("app.views.mount_interface.MessageBox")
        mock_box = MagicMock()
        mock_box.exec.return_value = True
        mock_box_cls.return_value = mock_box

        iface.deleteMount("dm")
        iface.mountManager.remove_mount.assert_called_once_with("dm")

    def test_delete_mount_cancel(self, iface, mocker):
        mock_box_cls = mocker.patch("app.views.mount_interface.MessageBox")
        mock_box = MagicMock()
        mock_box.exec.return_value = False
        mock_box_cls.return_value = mock_box

        iface.deleteMount("dm")
        iface.mountManager.remove_mount.assert_not_called()

    def test_do_mount(self, iface):
        iface.doMount("m1")
        iface.mountManager.mount.assert_called_once_with("m1")

    def test_do_unmount(self, iface):
        iface.doUnmount("u1")
        iface.mountManager.unmount.assert_called_once_with("u1")

    def test_mount_all(self, iface):
        m1 = MagicMock()
        m1.is_mounted = False
        m1.remote_name = "a"
        m2 = MagicMock()
        m2.is_mounted = True
        m2.remote_name = "b"
        m3 = MagicMock()
        m3.is_mounted = False
        m3.remote_name = "c"
        iface.mountManager.mounts = {"a": m1, "b": m2, "c": m3}

        iface.mountAll()

        calls = iface.mountManager.mount.call_args_list
        called_names = [c[0][0] for c in calls]
        assert "a" in called_names
        assert "c" in called_names
        assert "b" not in called_names

    def test_unmount_all(self, iface):
        iface.unmountAll()
        iface.mountManager.unmount_all.assert_called_once()

    def test_on_mount_status_changed(self, iface, mocker):
        mount = _make_mount(remote_name="sc1", drive_letter="X")
        mocker.patch.object(type(mount), "is_mounted", new_callable=lambda: property(lambda self: self.status == MountStatus.MOUNTED))
        iface.mountManager.mounts = {"sc1": mount}
        iface.loadMounts()
        iface.onMountStatusChanged("sc1", MountStatus.MOUNTED)
        assert iface.mountCards["sc1"].statusLabel.text() == "已挂载"

    def test_on_mount_status_changed_unknown_name(self, iface):
        iface.mountManager.mounts = {}
        iface.onMountStatusChanged("unknown", MountStatus.MOUNTED)

    def test_on_mount_error(self, iface, mocker):
        mock_infobar = mocker.patch("app.views.mount_interface.InfoBar")
        iface.onMountError("err_remote", "权限不足")
        mock_infobar.error.assert_called_once()
        args = mock_infobar.error.call_args
        assert "err_remote" in args[0][1]
