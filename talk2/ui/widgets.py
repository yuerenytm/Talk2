"""聊天界面用到的自定义控件：输入框与消息气泡。

只负责显示与输入，不含任何网络、存储或业务逻辑。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeyEvent, QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class Composer(QPlainTextEdit):
    """消息输入框：Enter 发送，Shift+Enter 换行。"""

    def __init__(self, on_submit, parent=None) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self.setPlaceholderText("输入消息，Enter 发送，Shift+Enter 换行")
        self.setFixedHeight(92)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            self._on_submit()
            return
        super().keyPressEvent(event)


class MessageBubble(QWidget):
    """一条消息：角色标签 + 气泡正文，可选引用列表。"""

    def __init__(self, role: str, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.role = role
        self._markdown = role == "assistant"
        self._text = text

        label = QLabel("你" if role == "user" else "Talk2")
        label.setStyleSheet("color: #8b909a; font-size: 12px;")

        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(True)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.body.document().setDocumentMargin(8)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        frame = QFrame()
        if role == "user":
            frame.setObjectName("userBubble")
        elif role == "error":
            frame.setObjectName("errorBubble")
            label.setText("出错")
        else:
            frame.setObjectName("assistantBubble")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(4, 2, 4, 2)
        inner.addWidget(self.body)

        self._col = QVBoxLayout()
        self._col.setContentsMargins(0, 0, 0, 0)
        self._col.setSpacing(4)
        self._col.addWidget(label)
        self._col.addWidget(frame)
        self._cite_box: QWidget | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 6, 16, 6)
        wrap = QWidget()
        wrap.setLayout(self._col)
        if role == "user":
            wrap.setMaximumWidth(920)
            row.addStretch(1)
            row.addWidget(wrap, 0)
        else:
            wrap.setMaximumWidth(1100)
            row.addWidget(wrap, 1)
            row.addSpacing(28)

        self.set_text(text, final=True)

    def set_text(self, text: str, final: bool = False) -> None:
        """设置气泡正文；final=True 时按最终样式渲染（含 Markdown）。
        """
        self._text = text
        if self._markdown and final:
            self.body.setMarkdown(text or " ")
        else:
            self.body.setPlainText(text or "")
        width = max(self.body.viewport().width(), 1)
        self.body.document().setTextWidth(width)
        height = int(self.body.document().size().height()) + 18
        self.body.setFixedHeight(max(height, 36))

    def set_citations(self, hits: list[dict[str, str]]) -> None:
        """在气泡下方渲染引用列表（可点击打开原文）。
        """
        if self._cite_box is not None:
            self._col.removeWidget(self._cite_box)
            self._cite_box.deleteLater()
            self._cite_box = None
        if not hits:
            return
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        caption = QLabel("引用")
        caption.setStyleSheet("color: #8b909a; font-size: 12px;")
        layout.addWidget(caption)
        for hit in hits:
            heading = hit.get("heading_path") or "正文"
            button = QPushButton(f"{hit.get('rel_path', '')}  ·  {heading}")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton { background: transparent; color: #8eb4ff; text-align: left; padding: 2px 0; }"
                "QPushButton:hover { color: #c5d8ff; }"
            )
            target = hit.get("abs_path", "")
            button.clicked.connect(lambda _checked=False, path=target: open_path(path))
            layout.addWidget(button)
        self._col.addWidget(box)
        self._cite_box = box


def open_path(path: str) -> None:
    """用系统默认程序打开本地文件。"""
    if path:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
