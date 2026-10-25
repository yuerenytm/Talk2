from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
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
)

from talk2.core import secrets
from talk2.core.llm_client import LLMConfig
from talk2.core.storage import Storage
from talk2.ui.chat_controller import ChatController
from talk2.ui.library_sync import LibrarySync
from talk2.ui.settings_window import SettingsDialog
from talk2.ui.widgets import Composer, MessageBubble


def _title_from(text: str) -> str:
    """用首条消息生成会话标题（截断并去换行）。
    """
    compact = " ".join(text.strip().split())
    if not compact:
        return "新对话"
    return compact[:24] + ("…" if len(compact) > 24 else "")


class ChatWindow(QMainWindow):
    """聊天主窗口：只负责布局、会话列表与把信号接到界面上。"""

    news_requested = Signal()

    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self.storage = storage
        self.current_id: int | None = None
        self._assistant_bubble: MessageBubble | None = None
        self._assistant_text = ""
        self._citations: list[dict[str, str]] = []
        self._settings: SettingsDialog | None = None
        self._tray_mode = False
        self._allow_quit = False

        self.chat = ChatController(self)
        self.chat.chunk.connect(self._on_chunk)
        self.chat.status.connect(self._show_status)
        self.chat.citations.connect(self._on_citations)
        self.chat.completed.connect(self._on_completed)
        self.chat.failed.connect(self._on_failed)
        self.chat.busy_changed.connect(self._on_busy_changed)

        self.library = LibrarySync(storage, self._llm_config, self)
        self.library.status.connect(self._show_index_status)

        self.setWindowTitle("Talk2")
        self.resize(1120, 740)
        self._build_ui()

        self._refresh_model_label()
        self._reload_sessions()
        self._new_chat()
        self.library.arm()
        if self.storage.get_setting("rag_enabled", "0") == "1":
            self.library.start(False)

    # ---------- 界面搭建 ----------

    def _build_ui(self) -> None:
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
        self.setStatusBar(QStatusBar())

    # ---------- 配置与状态 ----------

    def _llm_config(self) -> LLMConfig:
        """从数据库设置构造 LLMConfig（模型、地址、密钥、人设等）。
        """
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
        """是否有请求正在跑（按钮与发送入口都用它做闸门）。
        """
        return (
            self.chat.is_busy()
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

    def _show_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def _show_index_status(self, text: str) -> None:
        self.statusBar().showMessage(text)
        if self._settings is not None:
            self._settings.set_index_status(text)

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
        """打开设置窗口；关闭后刷新模型标签与索引状态。
        """
        dlg = SettingsDialog(self.storage, self)
        self._settings = dlg
        dlg.reindex_requested.connect(self._on_reindex_requested)
        dlg.news_requested.connect(self.news_requested.emit)
        saved = bool(dlg.exec())
        self._settings = None
        if saved:
            self._refresh_model_label()
            self.library.arm()
            if self.storage.get_setting("rag_path", ""):
                self.library.start(False)
            self.statusBar().showMessage("设置已保存", 3000)

    def _on_reindex_requested(self, force: bool) -> None:
        self.library.arm()
        self._refresh_model_label()
        self.library.start(force)

    # ---------- 会话 ----------

    def _reload_sessions(self, select_id: int | None = None) -> None:
        """重新加载会话列表，并把选中项切到 select_id。
        """
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
        """新建一个空会话（不落库，等第一条消息再创建）。
        """
        if self.chat.is_busy():
            return
        self.session_list.clearSelection()
        self.current_id = None
        self.title_label.setText("新对话")
        self._clear_messages()
        self._show_empty(True)

    def _delete_chat(self) -> None:
        """删除当前会话（二次确认），并清空消息区。
        """
        if self.chat.is_busy() or self.current_id is None:
            return
        if QMessageBox.question(self, "Talk2", "删除当前对话？") != QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_conversation(self.current_id)
        self._reload_sessions()
        self._new_chat()

    def _on_session_changed(self, current: QListWidgetItem | None, _prev) -> None:
        """会话列表切换时，加载对应历史。
        """
        if self.chat.is_busy() or current is None:
            return
        cid = current.data(Qt.ItemDataRole.UserRole)
        if cid is None:
            return
        self._load_conversation(int(cid))

    def _load_conversation(self, conversation_id: int) -> None:
        """从数据库读出全部消息并逐条重建气泡。
        """
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

    # ---------- 消息区 ----------

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
        """在消息区追加一个气泡并返回它。

        Args:
            role: user / assistant / error。
            text: 初始文本，流式时为空白。
            final: 是否已完成（影响样式与是否可继续追加）。
        """
        self._show_empty(False)
        bubble = MessageBubble(role, text)
        bubble.set_text(text, final=final)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _scroll_to_bottom(self) -> None:
        """把滚动条移到底部（流式输出时每来一段都调用）。
        """
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------- 发送与流式 ----------

    def _send(self) -> None:
        """发送入口：落库用户消息、准备会话、启动流式请求。

        顺序上先写数据库再上屏，保证界面异常时用户输入不丢；
        真正的网络请求交给 ChatController 在子线程执行。
        """
        if self.chat.is_busy():
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

        self.statusBar().showMessage("正在检索知识库…" if rag_query else "正在生成…")
        self.chat.send(cfg, payload, self.storage, rag_query, rag_root)

    def _on_busy_changed(self, busy: bool) -> None:
        """请求开始/结束时切换按钮与会话列表的可交互状态。
        """
        self.send_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        self.session_list.setEnabled(not busy)

    def _on_chunk(self, piece: str) -> None:
        """收到一段流式文本：累加后整体重设气泡内容（打字机效果的来源）。

        每次都全量 set_text 而不是追加，是为了让气泡自己处理换行与富文本。
        """
        self._assistant_text += piece
        if self._assistant_bubble:
            self._assistant_bubble.set_text(self._assistant_text, final=False)
        self._scroll_to_bottom()

    def _on_citations(self, hits: object) -> None:
        """收到检索引用：保存并渲染到助手气泡下方。
        """
        if not isinstance(hits, list):
            return
        self._citations = [item for item in hits if isinstance(item, dict)]
        if self._assistant_bubble:
            self._assistant_bubble.set_citations(self._citations)
        self._scroll_to_bottom()

    def _on_completed(self, text: str) -> None:
        """生成结束：展示最终文本，并把回答（含引用摘要）写入数据库。

        引用以文本形式拼在正文末尾——历史里不再保留结构化引用，
        这是当前的已知取舍。
        """
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

    def _citation_suffix(self) -> str:
        """把引用列表拼成 Markdown 片段，供落库与展示。
        """
        if not self._citations:
            return ""
        lines = ["", "---", "引用："]
        for item in self._citations:
            heading = item.get("heading_path") or "正文"
            lines.append(f"- `{item.get('rel_path', '')}` › {heading}")
        return "\n".join(lines)

    def _on_failed(self, message: str) -> None:
        """请求失败：先把已生成的部分存库，再追加一条错误气泡（错误本身不入库）。

        这样刷新历史时不会看到半截错误信息，但已产出的内容不会丢。
        """
        if self._assistant_text and self.current_id is not None:
            self.storage.add_message(self.current_id, "assistant", self._assistant_text)
        if self._assistant_bubble and self._assistant_text:
            self._assistant_bubble.set_text(self._assistant_text, final=True)
        self._append_bubble("error", message, final=True)
        self.statusBar().showMessage(message, 8000)

    def _stop(self) -> None:
        """请求停止：通知工作线程中断，等待其正常收尾。
        """
        if self.chat.is_busy():
            self.chat.stop()
            self.statusBar().showMessage("正在停止…")

    def closeEvent(self, event) -> None:
        """关闭窗口：托盘模式下仅隐藏；否则先停请求并释放控制器。
        """
        if self._tray_mode and not self._allow_quit:
            event.ignore()
            self.hide()
            return
        self.chat.dispose()
        self.library.dispose()
        super().closeEvent(event)
