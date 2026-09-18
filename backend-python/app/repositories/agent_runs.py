"""按业务域拆分的 SQLite 仓储；由 RepositoryHub 统一装配。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from app.agents.schemas import AgentEvent, utc_now


class AgentRunsRepositoryMixin:
    """持久化 Agent 运行、步骤、事件和工具调用审计。"""

    def create_run(
        self, run_id: str, owner: str, thread_id: str, request_type: str, objective: str, crop_scope: str
    ) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO agent_runs(id,owner_username,thread_id,request_type,objective,crop_scope,status,supervisor_id,started_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, owner, thread_id, request_type, objective, crop_scope, "RUNNING", "supervisor", utc_now()),
            )

    def save_event(self, event: AgentEvent) -> AgentEvent:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "INSERT INTO agent_events(run_id,step_id,agent_id,event_type,status,label,timestamp,duration_ms,data_summary) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    event.run_id,
                    event.step_id,
                    event.agent_id,
                    event.event_type,
                    event.status,
                    event.label,
                    event.timestamp,
                    event.duration_ms,
                    json.dumps(event.data_summary, ensure_ascii=False),
                ),
            )
            event.sequence = int(cursor.lastrowid)
            if event.event_type == "started":
                db.execute(
                    "INSERT OR IGNORE INTO agent_steps(id,run_id,sequence,agent_id,status,label,input_summary,started_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        event.step_id,
                        event.run_id,
                        event.sequence,
                        event.agent_id,
                        event.status,
                        event.label,
                        json.dumps(event.data_summary, ensure_ascii=False),
                        event.timestamp,
                    ),
                )
            elif event.event_type in {"completed", "failed", "skipped"}:
                # 部分确定性节点只有一个完成事件；先兜底插入再更新，保证 Step 与节点耗时可审计。
                db.execute(
                    "INSERT OR IGNORE INTO agent_steps(id,run_id,sequence,agent_id,status,label,input_summary,started_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        event.step_id,
                        event.run_id,
                        event.sequence,
                        event.agent_id,
                        event.status,
                        event.label,
                        "{}",
                        event.timestamp,
                    ),
                )
                db.execute(
                    "UPDATE agent_steps SET status=?,output_summary=?,finished_at=?,duration_ms=?,error_code=? WHERE id=?",
                    (
                        event.status,
                        json.dumps(event.data_summary, ensure_ascii=False),
                        event.timestamp,
                        event.duration_ms,
                        event.data_summary.get("errorCode"),
                        event.step_id,
                    ),
                )
        return event

    def finish_run(
        self, run_id: str, status: str, result: dict[str, Any], duration_ms: int, error_code: str | None = None
    ) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE agent_runs SET status=?,result_json=?,finished_at=?,duration_ms=?,model_calls=?,tool_calls=?,error_code=? WHERE id=?",
                (
                    status,
                    json.dumps(result, ensure_ascii=False),
                    utc_now(),
                    duration_ms,
                    result.get("modelCalls", 0),
                    result.get("toolCalls", 0),
                    error_code,
                    run_id,
                ),
            )

    def update_run_status(self, run_id: str, status: str, error_code: str | None = None) -> None:
        with self._lock, self.connect() as db:
            db.execute("UPDATE agent_runs SET status=?,error_code=? WHERE id=?", (status, error_code, run_id))

    def run_status(self, run_id: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT status FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        return None if row is None else str(row["status"])

    def list_runs(self, owner: str, admin: bool = False, status: str | None = None) -> list[dict[str, Any]]:
        clauses, args = [], []
        if not admin:
            clauses.append("owner_username=?")
            args.append(owner)
        if status:
            clauses.append("status=?")
            args.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as db:
            rows = db.execute(f"SELECT * FROM agent_runs{where} ORDER BY started_at DESC LIMIT 200", args).fetchall()
        return [self._run(row, include_result=False) for row in rows]

    def get_run(self, run_id: str, owner: str, admin: bool = False) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
            if row is None or (not admin and row["owner_username"] != owner):
                raise LookupError("未找到 Agent 运行记录或无权访问")
            steps = db.execute("SELECT * FROM agent_steps WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
            tool_calls = db.execute(
                "SELECT * FROM agent_tool_calls WHERE run_id=? ORDER BY started_at, id", (run_id,)
            ).fetchall()
        value = self._run(row, include_result=True)
        value["steps"] = [
            {
                **dict(step),
                "input_summary": self._json(step["input_summary"]),
                "output_summary": self._json(step["output_summary"]),
            }
            for step in steps
        ]
        # 采用新增响应字段而不改变旧 steps/result 结构，已有前端和 API 调用方可保持兼容。
        value["toolCallDetails"] = [
            {
                "id": call["id"],
                "runId": call["run_id"],
                "stepId": call["step_id"],
                "agentId": call["agent_id"],
                "toolName": call["tool_name"],
                "status": call["status"],
                "argsSummary": self._json(call["args_summary"]),
                "resultSummary": self._json(call["result_summary"]),
                "startedAt": call["started_at"],
                "finishedAt": call["finished_at"],
                "durationMs": call["duration_ms"],
                "errorCode": call["error_code"],
            }
            for call in tool_calls
        ]
        return value

    def events(self, run_id: str, owner: str, after: int = 0, admin: bool = False) -> list[dict[str, Any]]:
        self.get_run(run_id, owner, admin)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM agent_events WHERE run_id=? AND id>? ORDER BY id", (run_id, after)
            ).fetchall()
        return [{**dict(row), "sequence": row["id"], "dataSummary": self._json(row["data_summary"])} for row in rows]

    def save_tool_call(
        self,
        run_id: str,
        step_id: str,
        agent_id: str,
        tool_name: str,
        status: str,
        args_summary: dict[str, Any],
        result_summary: dict[str, Any] | None,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        error_code: str | None = None,
    ) -> str:
        call_id = str(uuid.uuid4())
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO agent_tool_calls VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    call_id,
                    run_id,
                    step_id,
                    agent_id,
                    tool_name,
                    status,
                    json.dumps(args_summary, ensure_ascii=False),
                    json.dumps(result_summary, ensure_ascii=False) if result_summary is not None else None,
                    started_at,
                    finished_at,
                    duration_ms,
                    error_code,
                ),
            )
        return call_id

    @staticmethod
    def _json(value: str | None) -> Any:
        return json.loads(value) if value else None

    def _run(self, row: sqlite3.Row, include_result: bool) -> dict[str, Any]:
        value = {
            "id": row["id"],
            "ownerUsername": row["owner_username"],
            "threadId": row["thread_id"],
            "requestType": row["request_type"],
            "objective": row["objective"],
            "cropScope": row["crop_scope"],
            "status": row["status"],
            "supervisorId": row["supervisor_id"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
            "durationMs": row["duration_ms"],
            "modelCalls": row["model_calls"],
            "toolCalls": row["tool_calls"],
            "errorCode": row["error_code"],
        }
        if include_result:
            value["result"] = self._json(row["result_json"])
        return value
