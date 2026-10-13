from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def tray_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor("#3d6dff"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "T2")
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, on_open, on_news, on_quit) -> None:
        super().__init__(tray_icon())
        self.setToolTip("Talk2")
        menu = QMenu()
        open_action = QAction("打开聊天", menu)
        open_action.triggered.connect(on_open)
        news_action = QAction("立即获取新闻", menu)
        news_action.triggered.connect(on_news)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(on_quit)
        menu.addAction(open_action)
        menu.addAction(news_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self._on_open = on_open

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._on_open()

    def notify(self, text: str) -> None:
        self.showMessage("Talk2", text, QSystemTrayIcon.MessageIcon.Information, 4000)
