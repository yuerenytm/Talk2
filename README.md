# Talk2

本地桌面 AI 助手。设计说明见 [doc/README.md](doc/README.md)。

当前已实现：PySide6 聊天窗口、OpenAI 兼容流式对话、多会话、SQLite 本地历史、API 设置（Key 写入系统凭据库）、对指定文件夹 Markdown 的本地 RAG、每日 RSS 新闻简报弹窗。

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

在设置里填写知识库路径并开启 RAG 后，对话会先检索该目录中的 Markdown，再交给模型回答。回答下方可点击引用打开原文件。Embedding 模型留空时使用关键词检索。

在设置里打开「每日新闻」并保存 RSS 后，可点「立即获取」预览简报。到了设定时刻会自动弹窗；关闭主窗口后程序留在托盘里。

数据目录：Windows 为 `%APPDATA%\Talk2\Talk2`，Linux 为 `~/.local/share/Talk2/`。

## 打包

在要发布的系统上安装构建依赖后执行 `python scripts/build.py`。Windows 也可运行 `scripts\build.ps1`。产物在 `dist/Talk2/`。说明见 [doc/打包.md](doc/打包.md)。

