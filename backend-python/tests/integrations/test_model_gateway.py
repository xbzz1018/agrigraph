from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

from app.integrations.model_gateway import ModelGateway


class FakeModel:
    def invoke(self, messages):
        assert messages[0] == ("system", "system prompt")
        return SimpleNamespace(
            content="answer",
            usage_metadata={"input_tokens": 1000, "output_tokens": 250, "total_tokens": 1250},
        )


def test_generate_returns_traceable_usage_and_estimated_cost(settings):
    gateway = ModelGateway(replace(settings, gateway_model="model-under-test", gateway_input_cost_per_million=2.0, gateway_output_cost_per_million=8.0))
    gateway._model = FakeModel()
    answer, usage = gateway.generate("system prompt", "untrusted")
    assert answer == "answer"
    assert usage["modelId"] == "model-under-test"
    assert usage["promptVersion"] == f"sha256:{hashlib.sha256(b'system prompt').hexdigest()}"
    assert usage["estimatedCostUsd"] == 0.004


def test_generate_marks_unknown_cost_without_pricing(settings):
    gateway = ModelGateway(settings)
    gateway._model = FakeModel()
    _, usage = gateway.generate("system prompt", "untrusted")
    assert usage["estimatedCostUsd"] is None
    assert usage["pricingConfigured"] is False
