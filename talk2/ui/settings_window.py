from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QPlainTextEdit,
)

from talk2.core import secrets
from talk2.core.storage import Storage


class SettingsDialog(QDialog):
    def __init__(self, storage: Storage, parent=None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("API 设置")
        self.setMinimumWidth(520)
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
        self.system_prompt.setFixedHeight(90)
        self.memory_only = QCheckBox("仅保存在当前进程内存（不写入系统凭据库）")

        form = QFormLayout()
        form.addRow("API 地址", self.base_url)
        form.addRow("模型", self.model)
        form.addRow("API Key", self.api_key)
        form.addRow("超时", self.timeout)
        form.addRow("温度", self.temperature)
        form.addRow("最大 Token", self.max_tokens)
        form.addRow("系统提示", self.system_prompt)

        hint = QLabel(
            "兼容 OpenAI 协议的服务都可以填：OpenAI、DeepSeek、通义兼容模式、Ollama（如 http://127.0.0.1:11434/v1）等。"
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
        layout.addWidget(buttons)
        self._load()

    def _load(self) -> None:
        s = self.storage
        self.base_url.setText(s.get_setting("base_url", "https://api.openai.com/v1"))
        self.model.setText(s.get_setting("model", ""))
        self.api_key.setText(secrets.get_api_key())
        self.timeout.setValue(int(s.get_setting("timeout", "60") or "60"))
        self.temperature.setValue(float(s.get_setting("temperature", "0.7") or "0.7"))
        self.max_tokens.setValue(int(s.get_setting("max_tokens", "0") or "0"))
        self.system_prompt.setPlainText(s.get_setting("system_prompt", ""))

    def _save(self) -> None:
        base = self.base_url.text().strip()
        model = self.model.text().strip()
        if not base or not model:
            QMessageBox.warning(self, "Talk2", "请填写 API 地址和模型名。")
            return
        self.storage.set_setting("base_url", base)
        self.storage.set_setting("model", model)
        self.storage.set_setting("timeout", str(self.timeout.value()))
        self.storage.set_setting("temperature", str(self.temperature.value()))
        self.storage.set_setting("max_tokens", str(self.max_tokens.value()))
        self.storage.set_setting("system_prompt", self.system_prompt.toPlainText().strip())
        backend = secrets.set_api_key(
            self.api_key.text(), persist=not self.memory_only.isChecked()
        )
        if backend == "memory":
            QMessageBox.information(
                self,
                "Talk2",
                "当前环境无法写入系统凭据库，API Key 只保存在本次运行的内存中。",
            )
        self.accept()
