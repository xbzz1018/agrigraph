"""调用远程视觉模型并校验结构化农业图片观察结果。"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.settings import Settings
from app.domain.models import VisionObservation


class VisionGateway:
    """OpenAI-compatible image analysis without retaining image bytes."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.settings.vision_api_base and self.settings.vision_api_key and self.settings.vision_model)

    def analyze(self, image_path: str | Path, crop_hint: str = "") -> VisionObservation:
        if not self.enabled:
            raise RuntimeError("VISION_NOT_CONFIGURED")
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError("diagnosis image is unavailable")
        data = path.read_bytes()
        if len(data) > 10 * 1024 * 1024:
            raise ValueError("diagnosis image exceeds 10 MB")
        mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
        payload = {
            "model": self.settings.vision_model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._prompt(crop_hint)},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"},
                        },
                    ],
                }
            ],
        }
        response = self._request(payload)
        content = response["choices"][0]["message"]["content"]
        return VisionObservation.model_validate(self._json_object(content))

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.vision_api_key}"}
        url = f"{self.settings.vision_api_base.rstrip('/')}/chat/completions"
        for attempt in range(2):
            try:
                if self._client is not None:
                    response = self._client.post(url, headers=headers, json=payload)
                else:
                    with httpx.Client(timeout=self.settings.vision_timeout_seconds) as client:
                        response = client.post(url, headers=headers, json=payload)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == 0:
                        time.sleep(1)
                        continue
                response.raise_for_status()
                return response.json()
            except httpx.TransportError:
                if attempt == 1:
                    raise
        raise RuntimeError("unreachable vision retry state")

    @staticmethod
    def _json_object(content: Any) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        text = str(content).strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1)
        else:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("vision response must be a JSON object")
        return value

    @staticmethod
    def _prompt(crop_hint: str) -> str:
        return (
            "Analyze only visible agricultural features. Return one JSON object with crop "
            "('番茄', '水稻', or '未知'), plantParts (string array), symptoms (string array), "
            "and qualityWarnings (string array). The crop hint is user-provided context: "
            f"{crop_hint[:80]!r}. For pest specimens, put visible insect morphology or feeding damage in symptoms "
            "even when no plant is visible, and add a quality warning. Do not name a disease, diagnose, or provide "
            "control advice. If the image is unclear, keep observations conservative."
        )
