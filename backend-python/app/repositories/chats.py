"""按业务域拆分的 SQLite 仓储；由 RepositoryHub 统一装配。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from app.agents.schemas import utc_now


class ChatsRepositoryMixin:
    """管理聊天会话、消息以及传给 MemoryAgent 的有界上下文。"""

    def create_session(self, owner: str, title: str, crop_scope: str, enhanced: bool) -> dict[str, Any]:
        now, session_id = utc_now(), str(uuid.uuid4())
        title = (title.strip() or "新农业对话")[:35]
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO chat_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, owner, title, crop_scope, int(enhanced), now, now),
            )
        return self.get_session_summary(owner, session_id)

    def list_sessions(self, owner: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM chat_sessions WHERE owner_username=? ORDER BY updated_at DESC", (owner,)
            ).fetchall()
        return [self._session(row) for row in rows]

    def get_session_summary(self, owner: str, session_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM chat_sessions WHERE id=? AND owner_username=?", (session_id, owner)
            ).fetchone()
        if row is None:
            raise LookupError("未找到农业对话或无权访问")
        return self._session(row)

    def get_session(self, owner: str, session_id: str) -> dict[str, Any]:
        session = self.get_session_summary(owner, session_id)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM chat_messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        return {"session": session, "messages": [self._message(row) for row in rows]}

    def update_session(self, owner: str, session_id: str, **values: Any) -> dict[str, Any]:
        current = self.get_session_summary(owner, session_id)
        title = values.get("title") or current["title"]
        crop = values.get("crop_scope") or current["cropScope"]
        enhanced = current["knowledgeEnhanced"] if values.get("enhanced") is None else values["enhanced"]
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE chat_sessions SET title=?,crop_scope=?,knowledge_enhanced=?,updated_at=? WHERE id=? AND owner_username=?",
                (title[:35], crop, int(enhanced), utc_now(), session_id, owner),
            )
        return self.get_session_summary(owner, session_id)

    def delete_session(self, owner: str, session_id: str) -> None:
        self.get_session_summary(owner, session_id)
        with self._lock, self.connect() as db:
            db.execute("DELETE FROM chat_sessions WHERE id=? AND owner_username=?", (session_id, owner))

    def add_message(
        self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "INSERT INTO chat_messages(session_id,role,content,answer_metadata,created_at) VALUES (?,?,?,?,?)",
                (session_id, role, content, json.dumps(metadata, ensure_ascii=False) if metadata else None, now),
            )
            row = db.execute("SELECT * FROM chat_messages WHERE id=?", (cursor.lastrowid,)).fetchone()
            db.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now, session_id))
        return self._message(row)

    def recent_messages(self, owner: str, session_id: str, limit: int = 6) -> list[dict[str, Any]]:
        self.get_session_summary(owner, session_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT role,content FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    @staticmethod
    def _json(value: str | None) -> Any:
        return json.loads(value) if value else None

    def _session(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "cropScope": row["crop_scope"],
            "knowledgeEnhanced": bool(row["knowledge_enhanced"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _message(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "createdAt": row["created_at"],
            "answer": self._json(row["answer_metadata"]),
        }
