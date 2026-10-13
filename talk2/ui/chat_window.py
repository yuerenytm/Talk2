from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent, QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QTextBrowser,
)

from talk2.core import secrets
from talk2.core.llm_client import LLMConfig
from talk2.core.rag import watch_directories
from talk2.core.storage import Storage
from talk2.ui.index_worker import IndexWorker
from talk2.ui.settings_window import SettingsDialog
from talk2.ui.stream_worker import StreamWorker


def _title_from(text: str) -> str:
    compact = " ".join(text.strip().split())
    if not compact:
        return "新对话"
    return compact[:24] + ("…" if len(compact) > 24 else "")


class Composer(QPlainTextEdit):
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
        col = self._col

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 6, 16, 6)
        wrap = QWidget()
        wrap.setLayout(col)
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
            button.clicked.connect(lambda _checked=False, path=target: _open_path(path))
            layout.addWidget(button)
        self._col.addWidget(box)
        self._cite_box = box


def _open_path(path: str) -> None:
    if path:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class ChatWindow(QMainWindow):
    news_requested = Signal()
    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self.storage = storage
        self.current_id: int | None = None
        self._thread: QThread | None = None
        self._worker: StreamWorker | None = None
        self._assistant_bubble: MessageBubble | None = None
        self._assistant_text = ""
        self._streaming = False
        self._citations: list[dict[str, str]] = []
        self._settings: SettingsDialog | None = None
        self._index_thread: QThread | None = None
        self._index_worker: IndexWorker | None = None
        self._index_pending_force: bool | None = None
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_library_changed)
        self._watcher.fileChanged.connect(self._on_library_changed)
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.setInterval(1500)
        self._watch_timer.timeout.connect(lambda: self.start_index(False))
        self._tray_mode = False
        self._allow_quit = False

        self.setWindowTitle("Talk2")
        self.resize(1120, 740)

        self.session_list = QListWidget()
        self.session_list.currentItemChanged.connect(self._on_session_changed)
        new_btn = QPushButton("新对话")
        new_btn.clicked.connect(self._new_chat)
        del_btn = QPushButton("删除")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_chat)

        side_btns = QHBoxLayout()
        side_btns.addWidget(new_btn)
        side_btns.addWidget(del_btn)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(260)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 12, 12, 12)
        brand = QLabel("Talk2")
        brand.setStyleSheet("font-size: 20px; font-weight: 600; padding: 4px 4px 12px 4px;")
        side_layout.addWidget(brand)
        side_layout.addLayout(side_btns)
        side_layout.addWidget(self.session_list, 1)

        self.title_label = QLabel("新对话")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.model_label = QLabel()
        self.model_label.setStyleSheet("color: #8b909a;")
        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(self.open_settings)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 12, 20, 12)
        header_left = QVBoxLayout()
        header_left.addWidget(self.title_label)
        header_left.addWidget(self.model_label)
        header_layout.addLayout(header_left, 1)
        header_layout.addWidget(settings_btn)

        self.empty = QLabel("在右侧设置里填入 API 地址、模型和 Key，然后开始对话。\nEnter 发送，Shift+Enter 换行。")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet("color: #8b909a; font-size: 14px;")

        self.msg_host = QWidget()
        self.msg_layout = QVBoxLayout(self.msg_host)
        self.msg_layout.setContentsMargins(8, 8, 8, 8)
        self.msg_layout.setSpacing(4)
        self.msg_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.msg_host)

        self.composer = Composer(self._send)
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primary")
        self.send_btn.setFixedWidth(88)
        self.send_btn.clicked.connect(self._send)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setFixedWidth(88)
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)

        input_bar = QFrame()
        input_bar.setObjectName("inputBar")
        input_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(16, 12, 16, 12)
        input_layout.setSpacing(10)
        input_layout.addWidget(self.composer, 1)
        btns = QVBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(8)
        btns.addWidget(self.send_btn, 1)
        btns.addWidget(self.stop_btn, 1)
        input_layout.addLayout(btns)

        self.empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        stage = QWidget()
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.addWidget(self.empty, 1)
        stage_layout.addWidget(self.scroll, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(header)
        right_layout.addWidget(stage, 1)
        right_layout.addWidget(input_bar)

        splitter = QSplitter()
        splitter.addWidget(sidebar)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 860])
        self.setCentralWidget(splitter)

        status = QStatusBar()
        self.setStatusBar(status)
        self._refresh_model_label()
        self._reload_sessions()
        self._new_chat()
        self._arm_watcher()
        if self.storage.get_setting("rag_enabled", "0") == "1":
            self.start_index(False)

    def _llm_config(self) -> LLMConfig:
        s = self.storage
        max_tokens = int(s.get_setting("max_tokens", "0") or "0")
        return LLMConfig(
            base_url=s.get_setting("base_url", "https://api.openai.com/v1"),
            api_key=secrets.get_api_key(),
            model=s.get_setting("model", ""),
            timeout=float(s.get_setting("timeout", "60") or "60"),
            temperature=float(s.get_setting("temperature", "0.7") or "0.7"),
            max_tokens=max_tokens or None,
            system_prompt=s.get_setting("system_prompt", ""),
            embedding_model=s.get_setting("embedding_model", ""),
        )

    def llm_config(self) -> LLMConfig:
        return self._llm_config()

    def is_busy(self) -> bool:
        return (
            self._streaming
            or self.composer.hasFocus()
            or bool(self.composer.toPlainText().strip())
        )

    def show_and_raise(self) -> None:
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def set_news_status(self, text: str) -> None:
        self.statusBar().showMessage(text)
        if self._settings is not None:
            self._settings.set_news_status(text)

    def set_tray_mode(self, enabled: bool) -> None:
        self._tray_mode = enabled

    def allow_quit(self) -> None:
        self._allow_quit = True

    def _refresh_model_label(self) -> None:
        cfg = self._llm_config()
        ready = "已配置" if cfg.api_key and cfg.model else "未配置 API"
        library = ""
        if self.storage.get_setting("rag_enabled", "0") == "1":
            folder = self.storage.get_setting("rag_path", "")
            if folder:
                library = f"  ·  知识库 {Path(folder).name}"
        self.model_label.setText(f"{cfg.model or '未填写模型'}  ·  {ready}{library}")

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.storage, self)
        self._settings = dlg
        dlg.reindex_requested.connect(self._on_reindex_requested)
        dlg.news_requested.connect(self.news_requested.emit)
        saved = bool(dlg.exec())
        self._settings = None
        if saved:
            self._refresh_model_label()
            self._arm_watcher()
            if self.storage.get_setting("rag_path", ""):
                self.start_index(False)
            self.statusBar().showMessage("设置已保存", 3000)

    def _reload_sessions(self, select_id: int | None = None) -> None:
        self.session_list.blockSignals(True)
        self.session_list.clear()
        for conv in self.storage.list_conversations():
            item = QListWidgetItem(conv.title)
            item.setData(Qt.ItemDataRole.UserRole, conv.id)
            self.session_list.addItem(item)
            if select_id is not None and conv.id == select_id:
                self.session_list.setCurrentItem(item)
        self.session_list.blockSignals(False)

    def _new_chat(self) -> None:
        if self._streaming:
            return
        self.session_list.clearSelection()
        self.current_id = None
        self.title_label.setText("新对话")
        self._clear_messages()
        self._show_empty(True)

    def _delete_chat(self) -> None:
        if self._streaming or self.current_id is None:
            return
        if QMessageBox.question(self, "Talk2", "删除当前对话？") != QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_conversation(self.current_id)
        self._reload_sessions()
        self._new_chat()

    def _on_session_changed(self, current: QListWidgetItem | None, _prev) -> None:
        if self._streaming or current is None:
            return
        cid = current.data(Qt.ItemDataRole.UserRole)
        if cid is None:
            return
        self._load_conversation(int(cid))

    def _load_conversation(self, conversation_id: int) -> None:
        conv = self.storage.get_conversation(conversation_id)
        if conv is None:
            return
        self.current_id = conv.id
        self.title_label.setText(conv.title)
        self._clear_messages()
        messages = self.storage.list_messages(conversation_id)
        self._show_empty(not messages)
        for msg in messages:
            self._append_bubble(msg.role, msg.content, final=True)

    def _clear_messages(self) -> None:
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._assistant_bubble = None
        self._assistant_text = ""

    def _show_empty(self, visible: bool) -> None:
        self.empty.setVisible(visible)
        self.scroll.setVisible(not visible)

    def _append_bubble(self, role: str, text: str, final: bool) -> MessageBubble:
        self._show_empty(False)
        bubble = MessageBubble(role, text)
        bubble.set_text(text, final=final)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _send(self) -> None:
        if self._streaming:
            return
        text = self.composer.toPlainText().strip()
        if not text:
            return
        cfg = self._llm_config()
        if not cfg.api_key or not cfg.model or not cfg.base_url:
            self.open_settings()
            return

        if self.current_id is None:
            conv = self.storage.create_conversation(_title_from(text))
            self.current_id = conv.id
            self.title_label.setText(conv.title)
            self._reload_sessions(conv.id)
        elif self.storage.get_conversation(self.current_id) and not self.storage.list_messages(self.current_id):
            self.storage.rename_conversation(self.current_id, _title_from(text))
            self.title_label.setText(_title_from(text))
            self._reload_sessions(self.current_id)

        self.storage.add_message(self.current_id, "user", text)
        self.composer.clear()
        self._append_bubble("user", text, final=True)

        self._assistant_text = ""
        self._citations = []
        self._assistant_bubble = self._append_bubble("assistant", "", final=False)
        payload = self.storage.chat_payload(self.current_id)
        rag_query = ""
        rag_root = ""
        if self.storage.get_setting("rag_enabled", "0") == "1":
            rag_root = self.storage.get_setting("rag_path", "")
            if rag_root:
                rag_query = text
        self._start_stream(cfg, payload, rag_query, rag_root)

    def _start_stream(
        self,
        cfg: LLMConfig,
        messages: list[dict[str, str]],
        rag_query: str = "",
        rag_root: str = "",
    ) -> None:
        self._streaming = True
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.session_list.setEnabled(False)
        self.statusBar().showMessage("正在检索知识库…" if rag_query else "正在生成…")

        self._thread = QThread(self)
        self._worker = StreamWorker(cfg, messages, self.storage, rag_query, rag_root)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.status.connect(self.statusBar().showMessage)
        self._worker.citations.connect(self._on_citations)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.completed.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_chunk(self, piece: str) -> None:
        self._assistant_text += piece
        if self._assistant_bubble:
            self._assistant_bubble.set_text(self._assistant_text, final=False)
        self._scroll_to_bottom()

    def _on_citations(self, hits: object) -> None:
        if not isinstance(hits, list):
            return
        self._citations = [item for item in hits if isinstance(item, dict)]
        if self._assistant_bubble:
            self._assistant_bubble.set_citations(self._citations)
        self._scroll_to_bottom()

    def _on_completed(self, text: str) -> None:
        final = text or self._assistant_text
        stored = final
        suffix = self._citation_suffix()
        if suffix:
            stored = f"{final}{suffix}" if final else suffix.lstrip()
        if self._assistant_bubble:
            self._assistant_bubble.set_text(final or "（无内容）", final=True)
            if self._citations:
                self._assistant_bubble.set_citations(self._citations)
        if self.current_id is not None and stored:
            self.storage.add_message(self.current_id, "assistant", stored)
        self.statusBar().showMessage("完成", 2500)
        self._end_stream()

    def _citation_suffix(self) -> str:
        if not self._citations:
            return ""
        lines = ["", "---", "引用："]
        for item in self._citations:
            heading = item.get("heading_path") or "正文"
            lines.append(f"- `{item.get('rel_path', '')}` › {heading}")
        return "\n".join(lines)

    def _on_failed(self, message: str) -> None:
        if self._assistant_text and self.current_id is not None:
            self.storage.add_message(self.current_id, "assistant", self._assistant_text)
        if self._assistant_bubble and self._assistant_text:
            self._assistant_bubble.set_text(self._assistant_text, final=True)
        self._append_bubble("error", message, final=True)
        self.statusBar().showMessage(message, 8000)
        self._end_stream()

    def _stop(self) -> None:
        if self._worker:
            self._worker.stop()
        self.statusBar().showMessage("正在停止…")

    def _end_stream(self) -> None:
        self._streaming = False
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.session_list.setEnabled(True)

    def _cleanup_worker(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None

    def _on_reindex_requested(self, force: bool) -> None:
        self._arm_watcher()
        self._refresh_model_label()
        self.start_index(force)

    def start_index(self, force: bool) -> None:
        root = self.storage.get_setting("rag_path", "").strip()
        if not root or not Path(root).is_dir():
            return
        if self._index_thread and self._index_thread.isRunning():
            pending = self._index_pending_force
            self._index_pending_force = force if pending is None else pending or force
            return
        self._index_thread = QThread(self)
        self._index_worker = IndexWorker(self.storage, root, self._llm_config(), force)
        self._index_worker.moveToThread(self._index_thread)
        self._index_thread.started.connect(self._index_worker.run)
        self._index_worker.status.connect(self._show_index_status)
        self._index_worker.finished.connect(self._on_index_finished)
        self._index_worker.failed.connect(self._on_index_failed)
        self._index_worker.finished.connect(self._index_thread.quit)
        self._index_worker.failed.connect(self._index_thread.quit)
        self._index_thread.finished.connect(self._cleanup_index)
        self._index_thread.start()
        self._show_index_status("正在建立索引…")

    def _show_index_status(self, text: str) -> None:
        self.statusBar().showMessage(text)
        if self._settings is not None:
            self._settings.set_index_status(text)

    def _on_index_finished(self, text: str) -> None:
        self._show_index_status(text)

    def _on_index_failed(self, text: str) -> None:
        self._show_index_status(f"索引失败：{text}")

    def _cleanup_index(self) -> None:
        pending = self._index_pending_force
        self._index_pending_force = None
        if self._index_worker:
            self._index_worker.deleteLater()
            self._index_worker = None
        if self._index_thread:
            self._index_thread.deleteLater()
            self._index_thread = None
        if pending is not None:
            QTimer.singleShot(0, lambda: self.start_index(pending))

    def _arm_watcher(self) -> None:
        current = self._watcher.directories() + self._watcher.files()
        if current:
            self._watcher.removePaths(current)
        if self.storage.get_setting("rag_enabled", "0") != "1":
            return
        root = self.storage.get_setting("rag_path", "").strip()
        if not root or not Path(root).is_dir():
            return
        paths = watch_directories(Path(root))
        if paths:
            self._watcher.addPaths(paths)

    def _on_library_changed(self, _path: str) -> None:
        if self.storage.get_setting("rag_enabled", "0") == "1":
            self._watch_timer.start()

    def closeEvent(self, event) -> None:
        if self._tray_mode and not self._allow_quit:
            event.ignore()
            self.hide()
            return
        if self._worker:
            self._worker.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1500)
        if self._index_thread and self._index_thread.isRunning():
            self._index_pending_force = None
            self._index_thread.quit()
            self._index_thread.wait(1500)
        super().closeEvent(event)
