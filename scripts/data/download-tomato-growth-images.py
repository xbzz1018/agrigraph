"""下载许可清晰的小规模番茄全生育期图片，并生成缩略图与来源清单。"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

from PIL import Image, ImageOps


def _data_root() -> Path:
    value = os.environ.get("AGRIGRAPH_DATA_ROOT", "").strip()
    if not value:
        raise RuntimeError("请先设置 AGRIGRAPH_DATA_ROOT，数据必须位于源码目录之外")
    return Path(value).expanduser().resolve()


DATA_ROOT = _data_root()
RAW_ROOT = DATA_ROOT / "raw/tomato-growth-stages"
THUMB_ROOT = DATA_ROOT / "processed/images/curated/tomato-growth-stages"
ROW_MANIFEST = DATA_ROOT / "processed/knowledge/tomato-growth-images.jsonl"
DATASET_MANIFEST = DATA_ROOT / "manifests/tomato-growth-images.json"
CHECKSUM_FILE = DATA_ROOT / "checksums/tomato-growth-images.sha256"
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "AgriGraph/1.0 (educational agricultural knowledge project)"

STAGES = [
    ("01苗期", "苗期", [
        "File:Tomato Seedling Full Resolution.jpg",
        "File:Expanded polystyrene tray with tomato seedlings.jpg",
        "File:Young seedling of tomato emerging from soil - India.jpg",
    ]),
    ("02营养生长期", "营养生长期", [
        "File:Natural plants of tomato.jpg",
        "File:Tomato plant 02.jpg",
        "File:Watering small tomato plants in a greenhouse.jpg",
    ]),
    ("03开花坐果期", "开花坐果期", [
        "File:Tomato Flower 2021.jpg",
        "File:Tomato flowers and young fruits - geograph.org.uk - 7201356.jpg",
        "File:Tomato tree with some flower.jpg",
    ]),
    ("04果实膨大期", "果实膨大期", [
        "File:Green Tomato plant.jpg",
        "File:Growing tomatoes 01.jpg",
        "File:Tomato plant (домати).jpg",
    ]),
    ("05转色期", "转色期", [
        "File:-2019-07-29 Ripening fruit on variety 'Sub Arctic Plenty' Tomato Plants, Trimingham.JPG",
        "File:-2021-09-06 Ripening fruit on variety 'Sub Arctic Plenty' Tomato Plants, Trimingham.JPG",
        "File:Ripening tomatoes on the plant.jpg",
    ]),
    ("06采收期", "采收期", [
        "File:A basket of freshly harvested tomatoes.jpg",
        "File:Tomatoes in basket 2022 G1.jpg",
        "File:Baskets of freshly harvested tomatoes at Pambeguwa perishable market 01.jpg",
    ]),
]

ALLOWED_LICENSES = ("CC BY", "CC0", "Public domain")


def request_json(params: dict[str, str]) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    result = subprocess.run(
        ["curl.exe", "--fail", "--location", "--silent", "--show-error",
         "--retry", "3", "--user-agent", USER_AGENT, url],
        check=True, capture_output=True,
    )
    return json.loads(result.stdout.decode("utf-8"))


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


def file_metadata(title: str) -> dict:
    payload = request_json({
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime",
        "iiurlwidth": "1280",
        "format": "json",
        "formatversion": "2",
        "origin": "*",
    })
    page = payload["query"]["pages"][0]
    if page.get("missing") is not None or not page.get("imageinfo"):
        raise RuntimeError(f"Wikimedia Commons 文件不存在：{title}")
    info = page["imageinfo"][0]
    metadata = info.get("extmetadata", {})
    license_name = metadata.get("LicenseShortName", {}).get("value", "")
    if not license_name.startswith(ALLOWED_LICENSES):
        raise RuntimeError(f"不允许的图片许可：{title} ({license_name})")
    return {
        "title": page["title"],
        "downloadUrl": info.get("thumburl") or info["url"],
        "originalUrl": info["url"],
        "sourcePage": info["descriptionurl"],
        "license": license_name,
        "licenseUrl": metadata.get("LicenseUrl", {}).get("value", ""),
        "artist": strip_html(metadata.get("Artist", {}).get("value", "未知作者")),
        "credit": strip_html(metadata.get("Credit", {}).get("value", "")),
        "description": strip_html(metadata.get("ImageDescription", {}).get("value", "")),
        "width": info.get("width", 0),
        "height": info.get("height", 0),
        "mime": info.get("mime", ""),
    }


def download(url: str, target: Path) -> None:
    if target.exists() and target.stat().st_size > 0:
        return
    temporary = target.with_suffix(target.suffix + ".part")
    for attempt in range(3):
        try:
            subprocess.run(
                ["curl.exe", "--fail", "--location", "--silent", "--show-error",
                 "--retry", "3", "--user-agent", USER_AGENT, "--output", str(temporary), url],
                check=True,
            )
            temporary.replace(target)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    THUMB_ROOT.mkdir(parents=True, exist_ok=True)
    ROW_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DATASET_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    CHECKSUM_FILE.parent.mkdir(parents=True, exist_ok=True)

    existing_rows = {}
    if ROW_MANIFEST.exists():
        existing_rows = {
            row["title"]: row
            for row in (json.loads(line) for line in ROW_MANIFEST.read_text(encoding="utf-8").splitlines())
        }
    rows: list[dict] = []
    checksums: list[str] = []
    expected_raw: set[Path] = set()
    expected_thumbs: set[Path] = set()
    for stage_dir, stage_name, titles in STAGES:
        raw_stage = RAW_ROOT / stage_dir
        thumb_stage = THUMB_ROOT / stage_dir
        raw_stage.mkdir(parents=True, exist_ok=True)
        thumb_stage.mkdir(parents=True, exist_ok=True)
        for index, title in enumerate(titles, start=1):
            cached = existing_rows.get(title)
            if cached:
                cached_raw = DATA_ROOT / cached["sourceFile"]
                cached_thumb = DATA_ROOT / cached["thumbnailFile"]
                if cached_raw.is_file() and cached_thumb.is_file():
                    rows.append(cached)
                    checksums.append(f"{cached['sha256']}  {cached['sourceFile']}")
                    expected_raw.add(cached_raw.resolve())
                    expected_thumbs.add(cached_thumb.resolve())
                    continue
            metadata = file_metadata(title)
            stable_id = hashlib.sha256(metadata["sourcePage"].encode("utf-8")).hexdigest()[:24]
            raw_file = raw_stage / f"{index:02d}-{stable_id}.jpg"
            thumb_file = thumb_stage / f"{stable_id}.webp"
            download(metadata["downloadUrl"], raw_file)
            with Image.open(raw_file) as image:
                converted = ImageOps.exif_transpose(image).convert("RGB")
                converted.thumbnail((960, 720), Image.Resampling.LANCZOS)
                converted.save(thumb_file, "WEBP", quality=78, method=6)
                display_width, display_height = converted.size
            relative_raw = raw_file.relative_to(DATA_ROOT).as_posix()
            relative_thumb = thumb_file.relative_to(DATA_ROOT).as_posix()
            digest = sha256(raw_file)
            checksums.append(f"{digest}  {relative_raw}")
            expected_raw.add(raw_file.resolve())
            expected_thumbs.add(thumb_file.resolve())
            rows.append({
                "id": stable_id,
                "datasetId": "tomato-growth-stages",
                "crop": "番茄",
                "stage": stage_name,
                "sourceFile": relative_raw,
                "thumbnailFile": relative_thumb,
                "thumbnailSizeBytes": thumb_file.stat().st_size,
                "sha256": digest,
                "displayWidth": display_width,
                "displayHeight": display_height,
                **metadata,
            })

    # 只清理本数据集目录中不再被当前精选清单引用的文件。
    for root, expected in ((RAW_ROOT, expected_raw), (THUMB_ROOT, expected_thumbs)):
        resolved_root = root.resolve()
        for candidate in root.rglob("*"):
            if candidate.is_file() and candidate.resolve().is_relative_to(resolved_root) and candidate.resolve() not in expected:
                candidate.unlink()

    with ROW_MANIFEST.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    CHECKSUM_FILE.write_text("\n".join(checksums) + "\n", encoding="utf-8")
    DATASET_MANIFEST.write_text(json.dumps({
        "id": "tomato-growth-stages",
        "title": "Curated Tomato Growth Stage Images",
        "chineseTitle": "番茄全生育期精选图片",
        "publisher": "Wikimedia Commons contributors",
        "source": "https://commons.wikimedia.org/",
        "licensePolicy": "仅收录 CC BY、CC BY-SA、CC0 或 Public Domain 文件，逐图保留许可和署名",
        "stageCount": len(STAGES),
        "imageCount": len(rows),
        "totalRawBytes": sum((DATA_ROOT / row["sourceFile"]).stat().st_size for row in rows),
        "totalThumbnailBytes": sum(row["thumbnailSizeBytes"] for row in rows),
        "manifest": ROW_MANIFEST.relative_to(DATA_ROOT).as_posix(),
        "checksumFile": CHECKSUM_FILE.relative_to(DATA_ROOT).as_posix(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stages": len(STAGES), "images": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
