import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "tests" / "evaluation"


def rows(name: str):
    return [json.loads(line) for line in (ROOT / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def test_image_fixture_has_required_strata_and_review_basis() -> None:
    values = rows("multimodal-image-test.jsonl")
    strata = Counter((row["crop"], row["usage"]) for row in values)
    assert len(values) == 30
    assert strata == Counter({("番茄", "DISEASE_CASE"): 8, ("番茄", "PEST_CASE"): 7, ("水稻", "DISEASE_CASE"): 7, ("水稻", "PEST_CASE"): 8})
    assert len({row["imageId"] for row in values}) == 30
    assert all(row["goldReviewMethod"] == "SOURCE_CURATED_PUBLIC_DATA" for row in values)


def test_control_fixture_has_required_strata_and_unique_relations() -> None:
    values = rows("control-relation-test.jsonl")
    strata = Counter((row["crop"], row["controlType"]) for row in values)
    assert len(values) == 30
    assert strata == Counter({
        ("番茄", "ACTIVE_INGREDIENT"): 8,
        ("番茄", "AGRICULTURAL"): 6,
        ("番茄", "BIOLOGICAL"): 1,
        ("水稻", "ACTIVE_INGREDIENT"): 7,
        ("水稻", "AGRICULTURAL"): 5,
        ("水稻", "BIOLOGICAL"): 3,
    })
    assert len({(row["diseaseId"], row["controlName"], row["controlType"]) for row in values}) == 30
