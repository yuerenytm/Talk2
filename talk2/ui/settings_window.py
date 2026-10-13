from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
)

from talk2.core import secrets
from talk2.core.news_fetcher import DEFAULT_FEEDS
from talk2.core.platform import set_autostart
from talk2.core.rag import status_line
from talk2.core.storage import Storage


class SettingsDialog(QDialog):
    reindex_requested = Signal(bool)
    news_requested = Signal()

    def __init__(self, storage: Storage, parent=None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("设置")
        self.setMinimumWidth(560)
        self.setModal(True)

        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://api.openai.com/v1")
        self.model = QLineEdit()
        self.model.setPlaceholderText("gpt-4o-mini 或 deepseek-chat")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-...")
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 600)
        self.timeout.setSuffix(" 秒")
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(0, 128000)
        self.max_tokens.setSpecialValueText("默认")
        self.system_prompt = QPlainTextEdit()
        self.system_prompt.setPlaceholderText("可选。会作为 system 消息加在每轮对话前。")
        self.system_prompt.setFixedHeight(72)
        self.memory_only = QCheckBox("仅保存在当前进程内存（不写入系统凭据库）")

        self.rag_enabled = QCheckBox("开启 RAG")
        self.rag_path = QLineEdit()
        self.rag_path.setPlaceholderText("选择包含 Markdown 的文件夹，例如 Obsidian 库")
        browse = QPushButton("浏览")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.rag_path, 1)
        path_row.addWidget(browse)
        self.embedding_model = QLineEdit()
        self.embedding_model.setPlaceholderText("可选，如 text-embedding-3-small；留空则只用关键词")
        self.index_status = QLabel()
        self.index_status.setWordWrap(True)
        self.index_status.setStyleSheet("color: #8b909a;")
        rebuild = QPushButton("重建索引")
        rebuild.clicked.connect(self._rebuild)

        self.news_enabled = QCheckBox("每日新闻")
        self.news_time = QTimeEdit()
        self.news_time.setDisplayFormat("HH:mm")
        self.news_feeds = QPlainTextEdit()
        self.news_feeds.setPlaceholderText("每行一个 RSS 地址")
        self.news_feeds.setFixedHeight(96)
        self.news_status = QLabel()
        self.news_status.setWordWrap(True)
        self.news_status.setStyleSheet("color: #8b909a;")
        fetch_news = QPushButton("立即获取")
        fetch_news.clicked.connect(self._fetch_news)
        self.autostart = QCheckBox("开机自启")

        form = QFormLayout()
        form.addRow("API 地址", self.base_url)
        form.addRow("模型", self.model)
        form.addRow("API Key", self.api_key)
        form.addRow("超时", self.timeout)
        form.addRow("温度", self.temperature)
        form.addRow("最大 Token", self.max_tokens)
        form.addRow("系统提示", self.system_prompt)
        form.addRow("知识库", self.rag_enabled)
        form.addRow("知识库路径", path_row)
        form.addRow("Embedding 模型", self.embedding_model)
        form.addRow("索引", self.index_status)
        form.addRow("新闻", self.news_enabled)
        form.addRow("推送时刻", self.news_time)
        form.addRow("RSS 源", self.news_feeds)
        form.addRow("简报", self.news_status)
        form.addRow("启动", self.autostart)

        hint = QLabel(
            "兼容 OpenAI 协议的服务都可以填：OpenAI、DeepSeek、通义兼容模式、Ollama（如 http://127.0.0.1:11434/v1）等。"
            "开启 RAG 后，对话会先在该文件夹的 Markdown 里检索，再交给模型回答。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b909a;")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.memory_only)
        layout.addWidget(rebuild)
        layout.addWidget(fetch_news)
        layout.addWidget(buttons)
        self._load()

    def set_index_status(self, text: str) -> None:
        self.index_status.setText(text)

    def set_news_status(self, text: str) -> None:
        self.news_status.setText(text)

    def _browse(self) -> None:
        start = self.rag_path.text().strip()
        path = QFileDialog.getExistingDirectory(self, "选择知识库目录", start)
        if path:
            self.rag_path.setText(path)

    def _load(self) -> None:
        s = self.storage
        self.base_url.setText(s.get_setting("base_url", "https://api.openai.com/v1"))
        self.model.setText(s.get_setting("model", ""))
        self.api_key.setText(secrets.get_api_key())
        self.timeout.setValue(int(s.get_setting("timeout", "60") or "60"))
        self.temperature.setValue(float(s.get_setting("temperature", "0.7") or "0.7"))
        self.max_tokens.setValue(int(s.get_setting("max_tokens", "0") or "0"))
        self.system_prompt.setPlainText(s.get_setting("system_prompt", ""))
        self.rag_enabled.setChecked(s.get_setting("rag_enabled", "0") == "1")
        self.rag_path.setText(s.get_setting("rag_path", ""))
        self.embedding_model.setText(s.get_setting("embedding_model", ""))
        self.index_status.setText(status_line(s))
        self.news_enabled.setChecked(s.get_setting("news_enabled", "0") == "1")
        parsed = QTime.fromString(s.get_setting("news_time", "08:00"), "HH:mm")
        self.news_time.setTime(parsed if parsed.isValid() else QTime(8, 0))
        self.news_feeds.setPlainText(s.get_setting("news_feeds", "") or DEFAULT_FEEDS.strip())
        self.autostart.setChecked(s.get_setting("autostart", "0") == "1")

    def _save(self) -> None:
        if self._persist():
            self.accept()

    def _rebuild(self) -> None:
        if not self._persist():
            return
        self.index_status.setText("正在建立索引…")
        self.reindex_requested.emit(True)

    def _fetch_news(self) -> None:
        if not self._persist():
            return
        self.news_status.setText("正在获取新闻…")
        self.news_requested.emit()

    def _persist(self) -> bool:
        base = self.base_url.text().strip()
        model = self.model.text().strip()
        if not base or not model:
            QMessageBox.warning(self, "Talk2", "请填写 API 地址和模型名。")
            return False
        path_text = self.rag_path.text().strip()
        enabled = self.rag_enabled.isChecked()
        if enabled and not path_text:
            QMessageBox.warning(self, "Talk2", "开启 RAG 前请先填写知识库路径。")
            return False
        resolved = ""
        if path_text:
            folder = Path(path_text)
            if not folder.is_dir():
                QMessageBox.warning(self, "Talk2", "知识库路径不是已存在的文件夹。")
                return False
            resolved = str(folder.resolve())

        self.storage.set_setting("base_url", base)
        self.storage.set_setting("model", model)
        self.storage.set_setting("timeout", str(self.timeout.value()))
        self.storage.set_setting("temperature", str(self.temperature.value()))
        self.storage.set_setting("max_tokens", str(self.max_tokens.value()))
        self.storage.set_setting("system_prompt", self.system_prompt.toPlainText().strip())
        self.storage.set_setting("rag_enabled", "1" if enabled else "0")
        self.storage.set_setting("rag_path", resolved)
        self.storage.set_setting("embedding_model", self.embedding_model.text().strip())
        self.storage.set_setting("news_enabled", "1" if self.news_enabled.isChecked() else "0")
        self.storage.set_setting("news_time", self.news_time.time().toString("HH:mm"))
        feeds = "\n".join(
            line.strip() for line in self.news_feeds.toPlainText().splitlines() if line.strip()
        )
        self.storage.set_setting("news_feeds", feeds or DEFAULT_FEEDS.strip())
        try:
            set_autostart(self.autostart.isChecked())
        except Exception as exc:
            QMessageBox.warning(self, "Talk2", f"开机自启未能更新：{exc}")
            return False
        self.storage.set_setting("autostart", "1" if self.autostart.isChecked() else "0")
        backend = secrets.set_api_key(
            self.api_key.text(), persist=not self.memory_only.isChecked()
        )
        if backend == "memory":
            QMessageBox.information(
                self,
                "Talk2",
                "当前环境无法写入系统凭据库，API Key 只保存在本次运行的内存中。",
            )
        return True
