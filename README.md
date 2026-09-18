# Talk2

本地桌面 AI 助手。设计说明见 [doc/README.md](doc/README.md)。

当前已实现：PySide6 聊天窗口、OpenAI 兼容流式对话、多会话、SQLite 本地历史、API 设置（Key 写入系统凭据库）。

## 运行

Windows 可双击项目里的 `Talk2.vbs`（无黑框）或 `Talk2.bat`，桌面上也会有 **Talk2** 快捷方式。


需要 Python 3.10+。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m talk2
```

Linux 下激活虚拟环境后同样执行 `pip install -r requirements.txt` 与 `python -m talk2`。

打开窗口后点「设置」，填写 API 地址、模型和 Key，即可对话。Enter 发送，Shift+Enter 换行。

数据目录：Windows 为 `%APPDATA%\Talk2\Talk2`，Linux 为 `~/.local/share/Talk2/`。

