"""精简项目的新建库结构；历史库额外表保持未使用状态。"""

INITIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password TEXT NOT NULL,
  role TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS token_sessions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, username TEXT NOT NULL, token_type TEXT NOT NULL,
  expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_token_sessions_user ON token_sessions(user_id, token_type);
CREATE TABLE IF NOT EXISTS chat_sessions (
  id TEXT PRIMARY KEY, owner_username TEXT NOT NULL, title TEXT NOT NULL,
  crop_scope TEXT NOT NULL, knowledge_enhanced INTEGER NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner_updated ON chat_sessions(owner_username, updated_at DESC);
CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT NOT NULL, answer_metadata TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);
CREATE TABLE IF NOT EXISTS agent_runs (
  id TEXT PRIMARY KEY, owner_username TEXT NOT NULL, thread_id TEXT NOT NULL, request_type TEXT NOT NULL,
  objective TEXT NOT NULL, crop_scope TEXT NOT NULL, status TEXT NOT NULL, supervisor_id TEXT NOT NULL,
  result_json TEXT, started_at TEXT NOT NULL, finished_at TEXT, duration_ms INTEGER,
  model_calls INTEGER NOT NULL DEFAULT 0, tool_calls INTEGER NOT NULL DEFAULT 0, error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_owner_started ON agent_runs(owner_username, started_at DESC);
CREATE TABLE IF NOT EXISTS agent_steps (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL, agent_id TEXT NOT NULL, status TEXT NOT NULL, label TEXT NOT NULL,
  input_summary TEXT, output_summary TEXT, started_at TEXT NOT NULL, finished_at TEXT,
  duration_ms INTEGER, error_code TEXT
);
CREATE TABLE IF NOT EXISTS agent_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  step_id TEXT NOT NULL, agent_id TEXT NOT NULL, event_type TEXT NOT NULL, status TEXT NOT NULL,
  label TEXT NOT NULL, timestamp TEXT NOT NULL, duration_ms INTEGER, data_summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_events_run_id ON agent_events(run_id, id);
CREATE TABLE IF NOT EXISTS agent_tool_calls (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  step_id TEXT NOT NULL, agent_id TEXT NOT NULL, tool_name TEXT NOT NULL, status TEXT NOT NULL,
  args_summary TEXT NOT NULL, result_summary TEXT, started_at TEXT NOT NULL, finished_at TEXT,
  duration_ms INTEGER, error_code TEXT
);
"""
