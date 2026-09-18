"""脱敏验证 DeepSeek 结构化输出和 Qwen3-VL 图片观察。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.core.settings import Settings
from app.domain.models import AgricultureQuery
from app.integrations.model_gateway import ModelGateway
from app.integrations.vision import VisionGateway


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sample_image(data_root: Path) -> tuple[Path, str]:
    knowledge = data_root / "processed" / "knowledge"
    entities = {str(item["id"]): item for item in _rows(knowledge / "agriculture-entities.jsonl")}
    candidates = []
    for item in _rows(knowledge / "image-entity-map.jsonl"):
        entity = entities.get(str(item.get("entityId", "")), {})
        crop = str(item.get("crop") or entity.get("crop") or "")
        relative = str(item.get("thumbnailFile") or item.get("sourceFile") or "")
        path = data_root / relative
        if (
            item.get("verificationStatus") == "VERIFIED"
            and item.get("usage") in {"DISEASE_CASE", "PEST_CASE"}
            and crop in {"番茄", "水稻"}
            and path.is_file()
        ):
            candidates.append((str(item.get("sha256") or ""), path, crop))
    if not candidates:
        raise FileNotFoundError("没有可用于视觉预检的核验图片")
    _, path, crop = sorted(candidates, key=lambda value: value[0])[0]
    return path, crop


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight DeepSeek and Qwen3-VL without exposing content or secrets.")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--env-file", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    load_dotenv(root / ".env.ai", override=False)
    if args.env_file:
        load_dotenv(Path(args.env_file), override=True)
    settings = Settings.from_env()
    model = ModelGateway(settings)
    vision = VisionGateway(settings)
    result: dict[str, Any] = {
        "kind": "agrigraph-multimodal-model-preflight",
        "deepseek": {"modelId": settings.gateway_model, "configured": model.enabled, "schemaValid": False},
        "vision": {"modelId": settings.vision_model, "configured": vision.enabled, "schemaValid": False},
    }
    if model.enabled:
        started = time.perf_counter()
        query, usage = model.structured(
            "将问题整理为 AgricultureQuery，只返回结构化字段。",
            "水稻叶片出现梭形病斑，可能是什么病害？",
            AgricultureQuery,
        )
        result["deepseek"].update(
            {
                "schemaValid": query is not None,
                "latencyMs": int((time.perf_counter() - started) * 1000),
                "tokenUsage": {
                    "inputTokens": usage.get("inputTokens"),
                    "outputTokens": usage.get("outputTokens"),
                    "totalTokens": usage.get("totalTokens"),
                },
            }
        )
    if vision.enabled:
        image_path, crop = _sample_image(Path(args.data_root).resolve())
        started = time.perf_counter()
        observation = vision.analyze(image_path, crop)
        result["vision"].update(
            {
                "schemaValid": observation.crop in {"番茄", "水稻", "未知"},
                "latencyMs": int((time.perf_counter() - started) * 1000),
            }
        )
    result["status"] = (
        "PASSED" if result["deepseek"]["schemaValid"] and result["vision"]["schemaValid"] else "FAILED"
    )
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
