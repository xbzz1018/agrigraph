"""从 Wikimedia Commons 下载小规模、许可明确的病虫害图片。"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def _data_root() -> Path:
    value = os.environ.get("AGRIGRAPH_DATA_ROOT", "").strip()
    if not value:
        raise RuntimeError("请先设置 AGRIGRAPH_DATA_ROOT，数据必须位于源码目录之外")
    return Path(value).expanduser().resolve()


DATA_ROOT = _data_root()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = PROJECT_ROOT / "config/datasets/verified-image-targets.json"
KNOWLEDGE_ROOT = DATA_ROOT / "processed/knowledge"
SOURCE_ROOT = DATA_ROOT / "processed/images/wikimedia-source"
THUMBNAIL_ROOT = DATA_ROOT / "processed/images/verified"
MANIFEST = KNOWLEDGE_ROOT / "supplemental-images.jsonl"
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "AgriGraph/1.0 (educational knowledge base; contact: local-project)"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_LICENSE_PREFIXES = ("cc0", "cc by ", "cc by-sa ", "public domain")
NON_CASE_TERMS = ("conidia", "fungus", "protein", "sporulation", "anniversary", "historical imagery", "wheat blast")
NON_PEST_CASE_TERMS = ("parasitoid", "eretmocerus", "trap", "trampa", "internal structures")


def api_request(params: dict[str, str | int], attempts: int = 4) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    result = subprocess.run(
        ["curl.exe", "-L", "--fail", "--silent", "--show-error", "--retry", str(min(attempts, 2)),
         "--retry-all-errors", "--retry-delay", "2", "--connect-timeout", "10", "--max-time", "30",
         "--user-agent", USER_AGENT, url],
        check=True, capture_output=True, text=True, encoding="utf-8", timeout=45,
    )
    return json.loads(result.stdout)


def download(url: str, target: Path) -> None:
    if target.is_file() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["curl.exe", "-L", "--fail", "--silent", "--show-error", "--retry", "2",
         "--retry-all-errors", "--retry-delay", "2", "--connect-timeout", "10", "--max-time", "60",
         "--user-agent", USER_AGENT, "--output", str(target), url],
        check=True, timeout=75,
    )


def clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def metadata_value(metadata: dict, key: str) -> str:
    return clean_html(str(metadata.get(key, {}).get("value", "")))


def allowed_license(value: str) -> bool:
    return any(value.lower().startswith(prefix) for prefix in ALLOWED_LICENSE_PREFIXES)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_entities() -> list[dict]:
    path = KNOWLEDGE_ROOT / "agriculture-entities.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def resolve_entity(name: str, entities: list[dict]) -> dict | None:
    return next((item for item in entities if item.get("name") == name), None)


def category_files(category: str) -> list[str]:
    result: list[str] = []
    continuation: str | None = None
    while len(result) < 40:
        params: dict[str, str | int] = {
            "action": "query", "format": "json", "list": "categorymembers",
            "cmtitle": f"Category:{category}", "cmtype": "file", "cmlimit": 40,
        }
        if continuation:
            params["cmcontinue"] = continuation
        payload = api_request(params)
        result.extend(item["title"] for item in payload.get("query", {}).get("categorymembers", []))
        continuation = payload.get("continue", {}).get("cmcontinue")
        if not continuation:
            break
        time.sleep(0.4)
    return result[:40]


def search_files(query: str) -> list[str]:
    if not query:
        return []
    payload = api_request({
        "action": "query", "format": "json", "list": "search", "srnamespace": 6,
        "srsearch": query, "srlimit": 30,
    })
    return [item["title"] for item in payload.get("query", {}).get("search", [])]


def image_records(titles: list[str]) -> list[dict]:
    records: list[dict] = []
    for start in range(0, len(titles), 20):
        payload = api_request({
            "action": "query", "format": "json", "titles": "|".join(titles[start:start + 20]),
            "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 1600,
        })
        records.extend(payload.get("query", {}).get("pages", {}).values())
        time.sleep(0.6)
    return records


def usable(record: dict, target: dict) -> tuple[bool, dict]:
    info = (record.get("imageinfo") or [{}])[0]
    metadata = info.get("extmetadata", {})
    license_name = metadata_value(metadata, "LicenseShortName")
    source_url = info.get("thumburl") or info.get("url", "")
    original_extension = Path(record.get("title", "")).suffix.lower()
    extension = Path(urllib.parse.urlparse(source_url).path).suffix.lower()
    if original_extension not in ALLOWED_EXTENSIONS or extension not in ALLOWED_EXTENSIONS or not allowed_license(license_name):
        return False, {}
    title = record.get("title", "").lower()
    searchable = " ".join([
        record.get("title", ""), metadata_value(metadata, "ImageDescription"),
        metadata_value(metadata, "Categories"), metadata_value(metadata, "ObjectName"),
    ]).lower()
    required_terms = [term.lower() for term in target.get("requiredTerms", [])]
    term_source = title if required_terms else searchable
    if required_terms and not any(term in term_source for term in required_terms):
        return False, {}
    if target.get("usage") == "DISEASE_CASE" and any(term in title for term in NON_CASE_TERMS):
        return False, {}
    if target.get("usage") == "PEST_CASE" and any(term in title for term in NON_PEST_CASE_TERMS):
        return False, {}
    return True, {
        "metadata": metadata, "license": license_name, "sourceUrl": source_url,
        "sourcePage": info.get("descriptionurl", ""),
    }


def convert_to_webp(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        image.save(target, "WEBP", quality=84, method=6)


def read_existing() -> dict[str, dict]:
    if not MANIFEST.exists():
        return {}
    return {
        row["id"]: row
        for row in (json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines())
        if row.get("id")
    }


def revalidate_existing(rows: dict[str, dict], targets: list[dict]) -> dict[str, dict]:
    target_by_entity = {target["entity"]: target for target in targets}
    valid: dict[str, dict] = {}
    for row_id, row in rows.items():
        target = target_by_entity.get(row.get("entityName", ""))
        if not target or Path(row.get("title", "")).suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        required_terms = [term.lower() for term in target.get("requiredTerms", [])]
        title = row.get("title", "").lower()
        if required_terms and not any(term in title for term in required_terms):
            continue
        if target.get("usage") == "DISEASE_CASE" and any(term in title for term in NON_CASE_TERMS):
            continue
        if target.get("usage") == "PEST_CASE" and any(term in title for term in NON_PEST_CASE_TERMS):
            continue
        valid[row_id] = row
    return valid


def save_manifest(rows: dict[str, dict]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in sorted(rows.values(), key=lambda value: (value.get("crop", ""), value.get("entityName", ""), value["id"])):
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(MANIFEST)


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    entities = read_entities()
    rows = revalidate_existing(read_existing(), config["targets"])
    save_manifest(rows)
    target_total = min(int(config["targetTotal"]), int(config["maximumTotal"]))
    if "--revalidate-only" in sys.argv:
        print(json.dumps({"verified": len(rows)}, ensure_ascii=False))
        return
    configured_targets = config["targets"]
    if "--pests-only" in sys.argv:
        configured_targets = [target for target in configured_targets if target["usage"] == "PEST_CASE"]

    for pass_index, entity_limit in enumerate((int(config["minimumPerEntity"]), int(config["perEntityLimit"]))):
        targets = configured_targets if pass_index == 0 else sorted(configured_targets, key=lambda value: value["usage"] != "PEST_CASE")
        for target in targets:
            if len(rows) >= target_total:
                break
            entity = resolve_entity(target["entity"], entities)
            if not entity:
                print(f"跳过未找到实体：{target['entity']}", flush=True)
                continue
            current = [row for row in rows.values() if row.get("entityId") == entity["id"]]
            remaining = min(entity_limit - len(current), target_total - len(rows))
            if remaining <= 0:
                continue
            try:
                titles = list(dict.fromkeys(category_files(target["category"]) + search_files(target.get("search", ""))))
                candidates = image_records(titles[:50])
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, TimeoutError) as error:
                print(f"获取 {target['entity']} 失败：{error}", flush=True)
                continue
            added = 0
            for candidate in candidates:
                accepted, details = usable(candidate, target)
                if not accepted:
                    continue
                stable_id = hashlib.sha256(details["sourcePage"].encode("utf-8")).hexdigest()[:24]
                if stable_id in rows:
                    continue
                extension = Path(urllib.parse.urlparse(details["sourceUrl"]).path).suffix.lower()
                source = SOURCE_ROOT / f"{stable_id}{extension}"
                thumbnail = THUMBNAIL_ROOT / f"{stable_id}.webp"
                try:
                    download(details["sourceUrl"], source)
                    convert_to_webp(source, thumbnail)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, UnidentifiedImageError) as error:
                    print(f"跳过损坏或不可下载图片 {candidate.get('title')}：{error}", flush=True)
                    source.unlink(missing_ok=True)
                    thumbnail.unlink(missing_ok=True)
                    continue
                metadata = details["metadata"]
                rows[stable_id] = {
                    "id": stable_id, "datasetId": "wikimedia-commons", "crop": target["crop"],
                    "sourceFile": source.relative_to(DATA_ROOT).as_posix(),
                    "thumbnailFile": thumbnail.relative_to(DATA_ROOT).as_posix(),
                    "usage": target["usage"], "verificationStatus": "VERIFIED",
                    "entityId": entity["id"], "entityName": entity["name"],
                    "entityType": entity["entityTypeCode"], "sourcePage": details["sourcePage"],
                    "author": metadata_value(metadata, "Artist") or "Wikimedia Commons contributor",
                    "license": details["license"], "licenseUrl": metadata_value(metadata, "LicenseUrl"),
                    "sha256": sha256(source), "title": candidate.get("title", "").removeprefix("File:"),
                }
                save_manifest(rows)
                added += 1
                print(f"已核验：{target['entity']} <- {candidate.get('title')}", flush=True)
                if added >= remaining:
                    break
            time.sleep(1.2)

    save_manifest(rows)
    coverage = {target["entity"]: sum(row.get("entityName") == target["entity"] for row in rows.values()) for target in config["targets"]}
    print(json.dumps({"downloaded": len(rows), "minimum": config["minimumTotal"], "coverage": coverage}, ensure_ascii=False, indent=2))
    if len(rows) < int(config["minimumTotal"]):
        print("警告：严格核验后的公开图片少于最低目标，不会用模糊图片补足。")


if __name__ == "__main__":
    main()
