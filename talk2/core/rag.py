from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from talk2.core.storage import Storage

SKIP_DIRS = {".obsidian", ".git", "node_modules", ".trash"}
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MAX_CHARS = 1200
OVERLAP = 80
TOP_K = 6
_PUNCT = set("，。！？、；：\"'“”‘’（）()[]【】《》<>…—-· \t\n\r")


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    rel_path: str#相对路径
    heading_path: str#标题路径
    content: str#内容
    abs_path: str#绝对路径


@dataclass(frozen=True)
class IndexReport:#索引报告
    files: int
    chunks: int
    read_errors: int
    embedded: int
    embed_note: str

    def summary(self) -> str:
        text = f"已索引 {self.files} 个文件、{self.chunks} 个段落"
        if self.read_errors:
            text += f"，{self.read_errors} 个文件未能读取"
        if self.embedded:
            text += f"，已写入 {self.embedded} 条语义向量"
        if self.embed_note:
            text += f"。{self.embed_note}"
        return text


def status_line(storage: Storage) -> str:
    """
    状态行
    """
    files, chunks = storage.kb_counts()
    when = storage.get_setting("kb_indexed_at", "")
    if files == 0 and not when:
        return "尚未建立索引"
    stamp = f"，更新于 {when}" if when else ""
    return f"已索引 {files} 个文件、{chunks} 个段落{stamp}"


def iter_markdown(root: Path):
    """遍历目录下的 Markdown 文件（跳过隐藏目录）。
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")]
        for name in filenames:
            if name.lower().endswith(".md"):
                yield Path(dirpath) / name


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """按标题层级切块并返回片段。

    超长段落会再按字符数切分，保留 overlap 以避免语义被截断。
    """
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    heading = ""
    in_fence = False

    def flush() -> None:
        body = "\n".join(buf).strip()
        buf.clear()
        if body:
            sections.append((heading, body))

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            buf.append(line)
            continue
        match = None if in_fence else HEADING.match(line)
        if match is None:
            buf.append(line)
            continue
        flush()
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        heading = " › ".join(name for _, name in stack)
    flush()

    merged: list[tuple[str, str]] = []
    carry = ""
    for section_heading, body in sections:
        if len(body) < 12:
            carry = " › ".join(part for part in (carry, section_heading) if part)
            continue
        if carry:
            section_heading = " › ".join(part for part in (carry, section_heading) if part)
            carry = ""
        merged.append((section_heading, body))
    if carry:
        if merged:
            last_heading, last_body = merged[-1]
            merged[-1] = (" › ".join(part for part in (last_heading, carry) if part), last_body)
        else:
            merged.append((carry, carry))

    pieces: list[tuple[str, str]] = []
    for section_heading, body in merged:
        pieces.extend(_split_long(section_heading, body))
    return pieces


def _split_long(heading: str, body: str) -> list[tuple[str, str]]:
    """
    分块长文本
    """
    if len(body) <= MAX_CHARS:
        return [(heading, body)]
    parts: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > MAX_CHARS:
            parts.append(current)
            current = current[-OVERLAP:] + "\n\n" + para
        else:
            current = para if not current else current + "\n\n" + para
        while len(current) > MAX_CHARS + 400:
            parts.append(current[:MAX_CHARS])
            current = current[MAX_CHARS - OVERLAP :]
    if current:
        parts.append(current)
    if len(parts) <= 1:
        return [(heading, parts[0] if parts else body)]
    labeled = []
    for index, part in enumerate(parts, start=1):
        title = f"{heading} ({index})" if heading else f"({index})"
        labeled.append((title, part))
    return labeled


def tokenize(text: str) -> list[str]:
    """中英混合分词：jieba 切中文 + 正则切英文/数字。
    """
    import jieba

    jieba.setLogLevel(logging.ERROR)
    tokens: list[str] = []
    for token in jieba.cut(text, cut_all=False):
        token = token.strip()
        if not token or all(ch in _PUNCT or ch.isspace() for ch in token):
            continue
        tokens.append(token)
    return tokens


def _fts_query(tokens: list[str]) -> str:
    """把查询词拼成 FTS5 的 MATCH 表达式（带引号转义）。
    """
    quoted = []
    for token in tokens[:12]:
        quoted.append('"' + token.replace('"', '""') + '"')
    return " OR ".join(quoted)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def index_library(
    storage: Storage,
    root: Path,
    embed_batch: Callable[[list[str]], list[list[float]]] | None = None,
    force: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> IndexReport:
    """增量索引：按 mtime 判断文件是否变化，只重建变化文件的分块。
    """
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"知识库目录不存在：{root}")

    previous = storage.get_setting("kb_root", "")
    if force or previous != str(root):
        storage.clear_kb()
        storage.set_setting("kb_root", str(root))

    current_model = storage.get_setting("embedding_model", "").strip()
    stored_model = storage.get_setting("kb_embedding_model", "")
    if current_model != stored_model:
        storage.clear_embeddings()
        storage.set_setting("kb_embedding_model", current_model)

    seen: set[str] = set()
    read_errors = 0
    paths = list(iter_markdown(root))
    for index, path in enumerate(paths, start=1):
        rel = path.relative_to(root).as_posix()
        seen.add(rel)
        stat = path.stat()
        old = storage.kb_file_mtime(rel)
        if not force and old is not None and abs(old - stat.st_mtime) < 1e-4:
            continue
        if on_status:
            on_status(f"正在索引 {index}/{len(paths)}：{rel}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            read_errors += 1
            continue
        rows = []
        for heading, content in chunk_markdown(text):
            body = " ".join(tokenize(f"{heading}\n{content}"))
            rows.append((heading, content, body))
        storage.replace_file_chunks(rel, stat.st_mtime, stat.st_size, rows)
    storage.delete_kb_files_not_in(seen)

    embedded = 0
    embed_note = ""
    if embed_batch and current_model:
        pending = storage.chunks_missing_embedding()
        batch: list[tuple[int, str]] = []
        try:
            for chunk_id, content in pending:
                batch.append((chunk_id, content[:6000]))
                if len(batch) >= 16:
                    embedded += _store_embeddings(storage, embed_batch, batch)
                    batch = []
                    if on_status:
                        on_status(f"正在写入语义向量 {embedded}/{len(pending)}")
            if batch:
                embedded += _store_embeddings(storage, embed_batch, batch)
        except Exception as exc:
            embed_note = f"语义向量未完成：{exc}"
    elif not current_model:
        embed_note = ""

    storage.set_setting("kb_indexed_at", _now())
    storage.set_setting("kb_read_errors", str(read_errors))
    files, chunks = storage.kb_counts()
    return IndexReport(files, chunks, read_errors, embedded, embed_note)


def _store_embeddings(
    storage: Storage,
    embed_batch: Callable[[list[str]], list[list[float]]],
    batch: list[tuple[int, str]],
) -> int:
    """
    存储语义向量
    """
    import json

    vectors = embed_batch([text for _, text in batch])
    if len(vectors) != len(batch):
        raise RuntimeError("embedding 返回数量与段落数量不一致")
    storage.set_embeddings(
        [(chunk_id, json.dumps(vector)) for (chunk_id, _), vector in zip(batch, vectors)]
    )
    return len(batch)


def search(
    storage: Storage,
    root: Path,
    query: str,
    embed_query: Callable[[str], list[float]] | None = None,
    top_k: int = TOP_K,
) -> list[Hit]:
    """混合检索：FTS5 关键词得分 + 向量余弦相似度，加权后取 Top-K。

    没有 embedding 时退化为纯关键词检索（当前默认配置即如此）。

    Returns:
        Hit 列表，按最终得分降序。
    """
    keyword_scores: dict[int, float] = {}#关键词得分
    tokens = tokenize(query)
    if tokens:
        rows = storage.search_keyword(_fts_query(tokens), limit=12)#搜索关键词
        if rows:
            best = max(score for _, score in rows) or 1.0
            for chunk_id, score in rows:
                keyword_scores[chunk_id] = score / best

    semantic_scores: dict[int, float] = {}
    if embed_query is not None:
        try:
            semantic_scores = _semantic_scores(storage, embed_query(query))
        except Exception:
            semantic_scores = {}

    ranked_ids = sorted(
        set(keyword_scores) | set(semantic_scores),
        key=lambda chunk_id: keyword_scores.get(chunk_id, 0.0) + semantic_scores.get(chunk_id, 0.0),
        reverse=True,
    )[:top_k]
    root = root.resolve()
    hits: list[Hit] = []
    for row in storage.get_chunks(ranked_ids):
        rel = str(row["rel_path"])
        hits.append(
            Hit(
                chunk_id=int(row["id"]),
                rel_path=rel,
                heading_path=str(row["heading_path"]),
                content=str(row["content"]),
                abs_path=str((root / rel).resolve()),
            )
        )
    return hits


def _semantic_scores(storage: Storage, query_vector: list[float]) -> dict[int, float]:
    """对候选分块计算查询向量与分块向量的余弦相似度。
    """
    import numpy as np

    items = storage.list_embeddings()#获取所有语义向量
    vectors = []
    ids = []
    width = len(query_vector)#获取查询向量的宽度
    for chunk_id, vector in items:
        if len(vector) != width:
            continue
        ids.append(chunk_id)#添加语义向量ID
        vectors.append(vector)#添加语义向量
    if not vectors:
        return {}#如果没有语义向量，返回空字典
    matrix = np.asarray(vectors, dtype=np.float32)#将语义向量转换为numpy数组
    query = np.asarray(query_vector, dtype=np.float32)#将查询向量转换为numpy数组
    query_norm = float(np.linalg.norm(query)) or 1.0#计算查询向量的范数
    norms = np.linalg.norm(matrix, axis=1)#计算语义向量矩阵的范数
    norms[norms == 0] = 1.0#将范数为0的元素替换为1.0
    sims = (matrix @ query) / (norms * query_norm)
    order = np.argsort(-sims)[:12]#将相似度按降序排序   
    best = float(sims[order[0]]) if len(order) else 1.0
    if best <= 0:
        return {}
    return {ids[int(pos)]: max(float(sims[int(pos)]), 0.0) / best for pos in order}#返回语义向量ID和相似度


def build_context(hits: list[Hit]) -> str:
    """把检索命中拼成系统提示用的上下文文本（带来源标题与字数上限）。
    """
    if not hits:
        return (
            "知识库中没有检索到与本次问题相关的段落。"
            "请直接说明库里没有对应内容，不要编造笔记中的细节。"
        )
    blocks = []
    for index, hit in enumerate(hits, start=1):
        title = hit.heading_path or "正文"
        blocks.append(f"[{index}] {hit.rel_path} › {title}\n{hit.content}")
    return (
        "下面是从用户本地 Markdown 知识库检索到的段落。"
        "请依据这些段落回答，并在用到某段时标注编号如 [1]。"
        "若段落里没有答案，直接说明库里没有对应内容。\n\n" + "\n\n".join(blocks)
    )


def watch_directories(root: Path, limit: int = 300) -> list[str]:
    root = root.resolve()
    found = [str(root)]
    for dirpath, dirnames, _filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")]
        for name in dirnames:
            found.append(str(Path(dirpath) / name))
            if len(found) >= limit:
                return found
    return found
