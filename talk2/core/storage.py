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
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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
