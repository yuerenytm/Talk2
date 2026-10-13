from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class NewsPopup(QWidget):
    def __init__(self, digest: dict, on_open: Callable[[], None] | None = None) -> None:
        super().__init__(None)
        self._on_open = on_open
        self.setWindowTitle("Talk2 新闻简报")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(520, 640)

        note = str(digest.get("note") or "")
        items = digest.get("items") or []
        header = QLabel("今日 10 条" if not note else note)
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        if note == "未摘要":
            header.setText("今日新闻（未摘要）")

        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        if not items:
            empty = QLabel(note or "这次没有取到新闻")
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #8b909a;")
            layout.addWidget(empty)
        for item in items:
            layout.addWidget(_item_card(item))
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        open_btn = QPushButton("打开助手")
        open_btn.setObjectName("primary")
        open_btn.clicked.connect(self._open_assistant)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(open_btn)
        buttons.addWidget(close_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.addWidget(header)
        root.addWidget(scroll, 1)
        root.addLayout(buttons)

    def present(self, activate: bool) -> None:
        self.show()
        self.raise_()
        if activate:
            self.activateWindow()

    def _open_assistant(self) -> None:
        if self._on_open:
            self._on_open()


def _item_card(item: dict) -> QFrame:
    frame = QFrame()
    frame.setObjectName("assistantBubble")
    layout = QVBoxLayout(frame)
    title = str(item.get("title") or "无标题")
    link = str(item.get("link") or "")
    button = QPushButton(title)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        "QPushButton { background: transparent; color: #e8eaed; text-align: left; font-weight: 600; padding: 0; }"
        "QPushButton:hover { color: #8eb4ff; }"
    )
    if link:
        button.clicked.connect(lambda _checked=False, url=link: QDesktopServices.openUrl(QUrl(url)))
    summary = QLabel(str(item.get("summary") or ""))
    summary.setWordWrap(True)
    source = QLabel(str(item.get("source") or ""))
    source.setStyleSheet("color: #8b909a;")
    layout.addWidget(button)
    if summary.text():
        layout.addWidget(summary)
    if source.text():
        layout.addWidget(source)
    return frame
