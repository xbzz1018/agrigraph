"""从公开原文中提取防治名称，并阻断具体施用参数。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ADVISORY = "具体用量和施用方式应以当地现行农药登记标签及农技人员指导为准。"

RESTRICTED_PATTERNS = (
    re.compile(r"\d+(?:\.\d+)?\s*%\s*[\u4e00-\u9fffA-Za-z0-9()（）-]{0,20}(?:剂|粉|液|油|唑|素|净|灵)"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:～|~|-)\s*\d+(?:\.\d+)?\s*(?:倍|毫升|ml|克|g|公斤|kg)", re.I),
    re.compile(r"\d+(?:\.\d+)?\s*(?:倍液|倍稀释液|毫升|ml|克|g|公斤|kg)\b", re.I),
    re.compile(r"(?:每亩|亩用|每公顷|公顷用|兑水|稀释|混配|混合使用|施药|喷药)"),
    re.compile(r"(?:每|间隔)\s*\d+\s*(?:天|次)"),
    re.compile(r"\d+(?:\.\d+)?\s*mg/kg", re.I),
)


def contains_restricted_usage(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in RESTRICTED_PATTERNS)


def asks_for_restricted_usage(text: str) -> bool:
    terms = ("剂量", "用量", "浓度", "倍液", "稀释", "兑水", "混配", "几次", "频次", "安全间隔")
    return any(term in (text or "") for term in terms)


def sanitize_answer(text: str, question: str = "") -> tuple[str, bool]:
    """删除包含施用参数的句段；询问剂量时只返回统一边界提示。"""

    if asks_for_restricted_usage(question):
        return ADVISORY, True
    segments = re.split(r"(?<=[。！？；;\n])", text or "")
    kept = [segment.strip() for segment in segments if segment.strip() and not contains_restricted_usage(segment)]
    changed = len(kept) != len([segment for segment in segments if segment.strip()])
    value = "".join(kept).strip()
    if changed:
        value = f"{value}\n{ADVISORY}".strip()
    return value or "当前证据不足，无法给出可靠的防治知识。", changed


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[3] / "config" / "ontology" / "control-options.json"
    return json.loads(path.read_text(encoding="utf-8"))


def extract_control_options(text: str, disease_id: str = "", disease_name: str = "") -> list[dict[str, Any]]:
    """只抽取经过配置归一化的名称，不返回原句和施用参数。"""

    value = text or ""
    options: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in _catalog()["activeIngredients"]:
        aliases = [item["name"], *item.get("aliases", [])]
        if not any(alias and alias in value for alias in aliases):
            continue
        key = (item["name"], "ACTIVE_INGREDIENT")
        if key not in seen:
            seen.add(key)
            options.append(_option(item["name"], "ACTIVE_INGREDIENT", disease_id, disease_name))
    for item in _catalog()["biologicalControls"]:
        aliases = [item["name"], *item.get("aliases", [])]
        if any(alias and alias in value for alias in aliases):
            key = (item["name"], "BIOLOGICAL")
            if key not in seen:
                seen.add(key)
                options.append(_option(item["name"], "BIOLOGICAL", disease_id, disease_name))
    if any(term in value for term in _catalog()["agriculturalKeywords"]):
        options.append(_option("农业防治原则", "AGRICULTURAL", disease_id, disease_name))
    return options


def extract_safe_control_principles(text: str) -> str:
    """保留不含具体施用参数的防治原则，供证据问答引用。"""

    forbidden_steps = (
        "浸种",
        "施药",
        "喷药",
        "喷雾",
        "药剂",
        "农药",
        "溶液",
        "兑水",
        "用药",
        "处理",
        "消毒",
        "浓度",
    )
    values: list[str] = []
    for segment in re.split(r"(?<=[。！？；;\n])", text or ""):
        cleaned = segment.strip()
        if (
            not cleaned
            or contains_restricted_usage(cleaned)
            or re.search(r"\d", cleaned)
            or any(term in cleaned for term in forbidden_steps)
        ):
            continue
        cleaned = re.sub(r"^(?:化学防治|药剂防治)[:：]?", "", cleaned).strip()
        if cleaned and cleaned not in values:
            values.append(cleaned[:500])
    return "".join(values)[:3000]


def _option(name: str, kind: str, disease_id: str, disease_name: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": kind,
        "targetDiseaseId": disease_id,
        "targetDiseaseName": disease_name,
        "evidenceIds": [f"doc:{disease_id}"] if disease_id else [],
    }
