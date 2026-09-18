from pathlib import Path

from app.domain.agriculture import AgricultureDomain


def test_image_case_candidates_returns_empty_for_missing_file(settings):
    domain = AgricultureDomain(settings)
    assert domain.image_case_candidates(Path("missing.webp")) == []
