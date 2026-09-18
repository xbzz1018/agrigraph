"""统一 API 响应和 SSE 序列化，避免各 Router 自行拼接协议。"""

from __future__ import annotations

import json
from typing import Any


def envelope(data: Any = None, message: str = "success", code: int = 200) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data}


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
