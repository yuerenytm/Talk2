from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Conversation:
    id: int
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Message:
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: str
    token_usage: str | None = None


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row#将查询结果转换为字典
        conn.execute("PRAGMA foreign_keys = ON")#启用外键约束
        conn.execute("PRAGMA journal_mode = WAL")#使用WAL模式，提高并发性能
        try:
            yield conn
            conn.commit()
        except Exception:#如果发生异常，回滚事务
            conn.rollback()
            raise
        finally:
            conn.close()#关闭连接

    def _init(self) -> None:
        with self._session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    token_usage TEXT,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kb_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rel_path TEXT NOT NULL UNIQUE,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kb_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    heading_path TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT,
                    FOREIGN KEY(file_id) REFERENCES kb_files(id) ON DELETE CASCADE
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(body);
                CREATE TABLE IF NOT EXISTS news_digests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fetched_at TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    raw_source_count INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    summarized INTEGER NOT NULL
                );
                """
            )

    def get_setting(self, key: str, default: str = "") -> str:
        with self._session() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def list_conversations(self) -> list[Conversation]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at "
                "FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [Conversation(**dict(row)) for row in rows]

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return Conversation(**dict(row)) if row else None

    def create_conversation(self, title: str = "新对话") -> Conversation:
        stamp = _now()
        with self._session() as conn:
            cur = conn.execute(
                "INSERT INTO conversations(title, created_at, updated_at) VALUES(?, ?, ?)",
                (title, stamp, stamp),
            )
            cid = int(cur.lastrowid)
        found = self.get_conversation(cid)
        assert found is not None
        return found

    def rename_conversation(self, conversation_id: int, title: str) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now(), conversation_id),
            )

    def delete_conversation(self, conversation_id: int) -> None:
        with self._session() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def list_messages(self, conversation_id: int) -> list[Message]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, role, content, created_at, token_usage "
                "FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
        return [Message(**dict(row)) for row in rows]

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        token_usage: str | None = None,
    ) -> Message:
        stamp = _now()
        with self._session() as conn:
            cur = conn.execute(
                "INSERT INTO messages(conversation_id, role, content, created_at, token_usage) "
                "VALUES(?, ?, ?, ?, ?)",
                (conversation_id, role, content, stamp, token_usage),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (stamp, conversation_id),
            )
            mid = int(cur.lastrowid)
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, conversation_id, role, content, created_at, token_usage "
                "FROM messages WHERE id = ?",
                (mid,),
            ).fetchone()
        assert row is not None
        return Message(**dict(row))

    def chat_payload(self, conversation_id: int) -> list[dict[str, str]]:
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.list_messages(conversation_id)
            if msg.role in {"system", "user", "assistant"}
        ]

    def clear_kb(self) -> None:
        with self._session() as conn:
            conn.execute("DELETE FROM kb_chunks_fts")
            conn.execute("DELETE FROM kb_chunks")
            conn.execute("DELETE FROM kb_files")

    def kb_file_mtime(self, rel_path: str) -> float | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT mtime FROM kb_files WHERE rel_path = ?", (rel_path,)
            ).fetchone()
        return float(row["mtime"]) if row else None

    def replace_file_chunks(
        self,
        rel_path: str,
        mtime: float,
        size: int,
        chunks: list[tuple[str, str, str]],
    ) -> None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT id FROM kb_files WHERE rel_path = ?", (rel_path,)
            ).fetchone()
            if row:
                file_id = int(row["id"])
                old_ids = [
                    int(item["id"])
                    for item in conn.execute(
                        "SELECT id FROM kb_chunks WHERE file_id = ?", (file_id,)
                    )
                ]
                for chunk_id in old_ids:
                    conn.execute("DELETE FROM kb_chunks_fts WHERE rowid = ?", (chunk_id,))
                conn.execute("DELETE FROM kb_chunks WHERE file_id = ?", (file_id,))
                conn.execute(
                    "UPDATE kb_files SET mtime = ?, size = ? WHERE id = ?",
                    (mtime, size, file_id),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO kb_files(rel_path, mtime, size) VALUES(?, ?, ?)",
                    (rel_path, mtime, size),
                )
                file_id = int(cur.lastrowid)
            for heading, content, body in chunks:
                cur = conn.execute(
                    "INSERT INTO kb_chunks(file_id, heading_path, content, embedding) "
                    "VALUES(?, ?, ?, NULL)",
                    (file_id, heading, content),
                )
                conn.execute(
                    "INSERT INTO kb_chunks_fts(rowid, body) VALUES(?, ?)",
                    (int(cur.lastrowid), body or "空"),
                )

    def delete_kb_files_not_in(self, rel_paths: set[str]) -> None:
        with self._session() as conn:
            rows = conn.execute("SELECT id, rel_path FROM kb_files").fetchall()
            for row in rows:
                if row["rel_path"] in rel_paths:
                    continue
                file_id = int(row["id"])
                old_ids = [
                    int(item["id"])
                    for item in conn.execute(
                        "SELECT id FROM kb_chunks WHERE file_id = ?", (file_id,)
                    )
                ]
                for chunk_id in old_ids:
                    conn.execute("DELETE FROM kb_chunks_fts WHERE rowid = ?", (chunk_id,))
                conn.execute("DELETE FROM kb_chunks WHERE file_id = ?", (file_id,))
                conn.execute("DELETE FROM kb_files WHERE id = ?", (file_id,))

    def kb_counts(self) -> tuple[int, int]:
        with self._session() as conn:
            files = conn.execute("SELECT COUNT(*) AS n FROM kb_files").fetchone()["n"]
            chunks = conn.execute("SELECT COUNT(*) AS n FROM kb_chunks").fetchone()["n"]
        return int(files), int(chunks)

    def search_keyword(self, match: str, limit: int) -> list[tuple[int, float]]:
        if not match.strip():
            return []
        with self._session() as conn:
            try:
                rows = conn.execute(
                    "SELECT rowid, bm25(kb_chunks_fts) AS score FROM kb_chunks_fts "
                    "WHERE kb_chunks_fts MATCH ? ORDER BY score LIMIT ?",
                    (match, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        return [(int(row["rowid"]), -float(row["score"])) for row in rows]

    def get_chunks(self, ids: list[int]) -> list[dict[str, str | int]]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        with self._session() as conn:
            rows = conn.execute(
                f"SELECT c.id, f.rel_path, c.heading_path, c.content "
                f"FROM kb_chunks c JOIN kb_files f ON f.id = c.file_id "
                f"WHERE c.id IN ({marks})",
                ids,
            ).fetchall()
        by_id = {int(row["id"]): row for row in rows}
        return [
            {
                "id": int(by_id[chunk_id]["id"]),
                "rel_path": str(by_id[chunk_id]["rel_path"]),
                "heading_path": str(by_id[chunk_id]["heading_path"]),
                "content": str(by_id[chunk_id]["content"]),
            }
            for chunk_id in ids
            if chunk_id in by_id
        ]

    def list_embeddings(self) -> list[tuple[int, list[float]]]:
        import json

        with self._session() as conn:
            rows = conn.execute(
                "SELECT id, embedding FROM kb_chunks "
                "WHERE embedding IS NOT NULL AND embedding != ''"
            ).fetchall()
        found: list[tuple[int, list[float]]] = []
        for row in rows:
            try:
                vector = json.loads(row["embedding"])
            except (TypeError, ValueError):
                continue
            if isinstance(vector, list) and vector:
                found.append((int(row["id"]), [float(item) for item in vector]))
        return found

    def chunks_missing_embedding(self) -> list[tuple[int, str]]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT id, heading_path, content FROM kb_chunks "
                "WHERE embedding IS NULL OR embedding = ''"
            ).fetchall()
        return [
            (int(row["id"]), f"{row['heading_path']}\n{row['content']}".strip())
            for row in rows
        ]

    def set_embeddings(self, pairs: list[tuple[int, str]]) -> None:
        if not pairs:
            return
        with self._session() as conn:
            conn.executemany(
                "UPDATE kb_chunks SET embedding = ? WHERE id = ?",
                [(embedding, chunk_id) for chunk_id, embedding in pairs],
            )

    def clear_embeddings(self) -> None:
        with self._session() as conn:
            conn.execute("UPDATE kb_chunks SET embedding = NULL")

    def add_news_digest(
        self,
        items_json: str,
        raw_source_count: int,
        model: str,
        summarized: bool,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO news_digests(fetched_at, items_json, raw_source_count, model, summarized) "
                "VALUES(?, ?, ?, ?, ?)",
                (_now(), items_json, raw_source_count, model, 1 if summarized else 0),
            )
