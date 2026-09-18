"""基础用户身份与 JWT 撤销记录仓储。"""

from __future__ import annotations

import sqlite3
from typing import Any

from app.agents.schemas import utc_now


class UsersRepositoryMixin:
    def create_user(self, username: str, password_hash: str, role: str = "USER") -> dict[str, Any]:
        now = utc_now()
        with self._lock, self.connect() as db:
            try:
                db.execute(
                    "INSERT INTO users(username,password,role,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (username, password_hash, role, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Username already exists") from exc
        return self.get_user(username)

    def get_user(self, username: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row is None:
            raise LookupError("User not found")
        return self._user(row, include_password=True)

    def update_password(self, username: str, password_hash: str, role: str | None = None) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self.connect() as db:
            row = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if row is None:
                raise LookupError("User not found")
            if role is None:
                db.execute("UPDATE users SET password=?,updated_at=? WHERE username=?", (password_hash, now, username))
            else:
                db.execute(
                    "UPDATE users SET password=?,role=?,updated_at=? WHERE username=?",
                    (password_hash, role, now, username),
                )
        return self.user_view(username)

    def user_view(self, username: str) -> dict[str, Any]:
        value = self.get_user(username)
        value.pop("password", None)
        return value

    def list_users(self, keyword: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]:
        where, args = (" WHERE username LIKE ?", [f"%{keyword}%"]) if keyword else ("", [])
        offset = max(0, page - 1) * page_size
        with self.connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM users{where}", args).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM users{where} ORDER BY id LIMIT ? OFFSET ?", args + [page_size, offset]
            ).fetchall()
        return {
            "content": [
                {
                    "userId": str(row["id"]),
                    "username": row["username"],
                    "email": "",
                    "status": 1,
                    "createTime": row["created_at"],
                    "lastLoginTime": row["updated_at"],
                }
                for row in rows
            ],
            "totalElements": total,
            "number": page - 1,
            "size": page_size,
        }

    def conversation_messages(self, user_id: int, start_date: str, end_date: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            user = db.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
            if user is None:
                return []
            rows = db.execute(
                "SELECT m.role,m.content,m.created_at FROM chat_messages m JOIN chat_sessions s ON s.id=m.session_id "
                "WHERE s.owner_username=? AND date(m.created_at)>=date(?) AND date(m.created_at)<=date(?) ORDER BY m.id",
                (user["username"], start_date, end_date),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"], "timestamp": row["created_at"]} for row in rows]

    def save_token(self, token_id: str, user_id: str, username: str, token_type: str, expires_at: str) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO token_sessions VALUES(?,?,?,?,?,?,?)",
                (token_id, user_id, username, token_type, expires_at, None, utc_now()),
            )

    def token_active(self, token_id: str, token_type: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT 1 FROM token_sessions WHERE id=? AND token_type=? AND revoked_at IS NULL AND expires_at>?",
                (token_id, token_type, utc_now()),
            ).fetchone()
        return row is not None

    def revoke_token(self, token_id: str) -> None:
        with self._lock, self.connect() as db:
            db.execute("UPDATE token_sessions SET revoked_at=? WHERE id=?", (utc_now(), token_id))

    def revoke_user_tokens(self, user_id: str) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE token_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (utc_now(), user_id)
            )

    @staticmethod
    def _user(row: sqlite3.Row, include_password: bool = False) -> dict[str, Any]:
        value = {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        if include_password:
            value["password"] = row["password"]
        return value
