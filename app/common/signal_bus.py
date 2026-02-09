import logging

from PySide6.QtCore import QObject, Signal, QThread

logger = logging.getLogger(__name__)


class SignalBus(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)
        if not QThread.currentThread().isMainThread():
            logger.warning("SignalBus 在非主线程中初始化，可能会导致问题")

    themeChanged = Signal()

    remoteAdded = Signal(str)
    remoteRemoved = Signal(str)
    remoteUpdated = Signal(str)

    mountStarted = Signal(str, str)
    mountStopped = Signal(str)
    mountError = Signal(str, str)

    syncStarted = Signal(str)
    syncProgress = Signal(str, int, int, int)
    syncStatsUpdate = Signal(str, dict)
    syncCompleted = Signal(str, bool, str)
    syncError = Signal(str, str)
    scheduledTaskDue = Signal(str, str)

    switchToInterface = Signal(str)

    showMainWindow = Signal()
    hideMainWindow = Signal()


signalBus = SignalBus()
