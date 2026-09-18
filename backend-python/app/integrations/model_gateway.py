"""DeepSeek 文本模型边界，负责结构化理解和证据回答。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.settings import Settings

T = TypeVar("T", bound=BaseModel)


class ModelGateway:
    """OpenAI 兼容文本模型边界；异常时由工作流使用确定性降级。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        if settings.gateway_api_key:
            from langchain_openai import ChatOpenAI

            self._model = ChatOpenAI(
                api_key=settings.gateway_api_key,
                base_url=settings.gateway_api_base,
                model=settings.gateway_model,
                temperature=0,
                timeout=settings.model_timeout_seconds,
                max_retries=1,
            )

    @property
    def enabled(self) -> bool:
        return self._model is not None

    def structured(self, system: str, user: str, schema: type[T]) -> tuple[T | None, dict[str, Any]]:
        if self._model is None:
            return None, {}
        try:
            response = self._model.with_structured_output(schema, include_raw=True).invoke(
                [("system", system), ("user", self._untrusted(user))]
            )
            parsed = response.get("parsed") if isinstance(response, dict) else response
            value = parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
            raw = response.get("raw") if isinstance(response, dict) else None
            return value, self._usage(raw, system)
        except Exception:
            return None, {}

    def generate(self, system: str, user: str) -> tuple[str | None, dict[str, Any]]:
        if self._model is None:
            return None, {}
        try:
            response = self._model.invoke([("system", system), ("user", self._untrusted(user))])
            return str(response.content), self._usage(response, system)
        except Exception:
            return None, {}

    def _usage(self, response: Any, system: str) -> dict[str, Any]:
        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        pricing_configured = bool(
            self.settings.gateway_input_cost_per_million or self.settings.gateway_output_cost_per_million
        )
        estimated_cost = None
        if pricing_configured:
            estimated_cost = (
                input_tokens * self.settings.gateway_input_cost_per_million
                + output_tokens * self.settings.gateway_output_cost_per_million
            ) / 1_000_000
        return {
            "modelId": self.settings.gateway_model,
            "promptVersion": f"sha256:{hashlib.sha256(system.encode('utf-8')).hexdigest()}",
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": int(usage.get("total_tokens", input_tokens + output_tokens)),
            "estimatedCostUsd": round(estimated_cost, 8) if estimated_cost is not None else None,
            "pricingConfigured": pricing_configured,
        }

    @staticmethod
    def evidence_payload(items: list[dict[str, Any]]) -> str:
        safe = [
            {
                "id": item.get("id"),
                "type": item.get("source_type"),
                "title": str(item.get("title", ""))[:160],
                "excerpt": str(item.get("excerpt", ""))[:1200],
                "score": item.get("score"),
            }
            for item in items[:12]
        ]
        return json.dumps(safe, ensure_ascii=False)

    @staticmethod
    def _untrusted(value: str) -> str:
        return f"<UNTRUSTED_DATA>\n{value[:24000]}\n</UNTRUSTED_DATA>"
