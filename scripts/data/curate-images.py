"""从本地原始图片中去重并生成小规模 WebP 展示集。"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict, deque
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


def _data_root() -> Path:
    value = os.environ.get("AGRIGRAPH_DATA_ROOT", "").strip()
    if not value:
        raise RuntimeError("请先设置 AGRIGRAPH_DATA_ROOT，数据必须位于源码目录之外")
    return Path(value).expanduser().resolve()


DATA_ROOT = _data_root()
INVENTORY = DATA_ROOT / "processed/knowledge/image-inventory.jsonl"
OUTPUT_ROOT = DATA_ROOT / "processed/images/curated"
OUTPUT_MANIFEST = DATA_ROOT / "processed/knowledge/image-curated.jsonl"

LIMITS = {
    "tomato-multimodal": 150,
    "tomato-leaf-disease": 150,
    "rice-phenology": 100,
    "crop-phenology-images": 100,
}


def difference_hash(image: Image.Image) -> int:
    gray = ImageOps.grayscale(image).resize((9, 8))
    pixels = list(gray.get_flattened_data())
    bits = 0
    for row in range(8):
        for column in range(8):
            bits = (bits << 1) | int(
                pixels[row * 9 + column] > pixels[row * 9 + column + 1]
            )
    return bits


def is_near_duplicate(value: int, selected: list[int]) -> bool:
    return any((value ^ candidate).bit_count() <= 4 for candidate in selected)


def group_name(source_file: str) -> str:
    parts = Path(source_file).parts
    return "/".join(parts[-3:-1]) if len(parts) >= 3 else "unknown"


def round_robin(rows: list[dict]) -> list[dict]:
    groups: dict[str, deque[dict]] = defaultdict(deque)
    for row in sorted(rows, key=lambda item: item["sourceFile"]):
        groups[group_name(row["sourceFile"])].append(row)
    ordered: list[dict] = []
    queues = [groups[name] for name in sorted(groups)]
    while queues:
        active: list[deque[dict]] = []
        for queue in queues:
            if queue:
                ordered.append(queue.popleft())
            if queue:
                active.append(queue)
        queues = active
    return ordered


def main() -> None:
    if not INVENTORY.exists():
        raise FileNotFoundError(f"图片清单不存在：{INVENTORY}")
    inventory = [json.loads(line) for line in INVENTORY.read_text(encoding="utf-8").splitlines()]
    by_dataset: dict[str, list[dict]] = defaultdict(list)
    for row in inventory:
        by_dataset[row["datasetId"]].append(row)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    selected_rows: list[dict] = []
    rejected = defaultdict(int)

    for dataset_id, limit in LIMITS.items():
        hashes: list[int] = []
        count = 0
        for row in round_robin(by_dataset.get(dataset_id, [])):
            if count >= limit:
                break
            source = DATA_ROOT / row["sourceFile"]
            try:
                with Image.open(source) as image:
                    image.load()
                    if min(image.size) < 224:
                        rejected["lowResolution"] += 1
                        continue
                    value = difference_hash(image)
                    if is_near_duplicate(value, hashes):
                        rejected["nearDuplicate"] += 1
                        continue
                    hashes.append(value)
                    target_dir = OUTPUT_ROOT / dataset_id
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_name = hashlib.sha256(row["sourceFile"].encode("utf-8")).hexdigest()[:20] + ".webp"
                    target = target_dir / target_name
                    converted = ImageOps.exif_transpose(image).convert("RGB")
                    converted.thumbnail((512, 512), Image.Resampling.LANCZOS)
                    converted.save(target, "WEBP", quality=72, method=6)
            except (UnidentifiedImageError, OSError, ValueError):
                rejected["damaged"] += 1
                continue

            selected_rows.append(
                {
                    **row,
                    "thumbnailFile": str(target.relative_to(DATA_ROOT)).replace("\\", "/"),
                    "thumbnailSizeBytes": target.stat().st_size,
                    "perceptualHash": f"{value:016x}",
                }
            )
            count += 1

    with OUTPUT_MANIFEST.open("w", encoding="utf-8", newline="\n") as stream:
        for row in selected_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "selected": len(selected_rows),
        "thumbnailBytes": sum(row["thumbnailSizeBytes"] for row in selected_rows),
        "byDataset": {
            dataset_id: sum(row["datasetId"] == dataset_id for row in selected_rows)
            for dataset_id in LIMITS
        },
        "rejected": dict(rejected),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
