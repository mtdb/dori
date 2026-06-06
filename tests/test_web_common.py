import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_common():
    path = ROOT / "boilerplate" / "scripts" / "_web_common.py"
    spec = importlib.util.spec_from_file_location("_web_common_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_freshness_accepts_supported_values() -> None:
    common = load_common()

    assert common.normalize_freshness(None) is None
    assert common.normalize_freshness("week") == "week"


def test_normalize_freshness_rejects_unknown_value() -> None:
    common = load_common()

    with pytest.raises(ValueError, match="Unsupported freshness"):
        common.normalize_freshness("hour")


def test_normalize_evidence_deduplicates_and_bounds_fields() -> None:
    common = load_common()
    results = [
        {"title": "One", "url": "https://example.com/1", "snippet": "A" * 900},
        {"title": "Duplicate", "url": "https://example.com/1", "snippet": "ignored"},
        {"title": "Two", "url": "https://example.com/2", "snippet": "second"},
        {"title": "No URL", "url": "", "snippet": "ignored"},
    ]

    evidence = common.normalize_evidence(results)

    assert [item["url"] for item in evidence] == [
        "https://example.com/1",
        "https://example.com/2",
    ]
    assert len(evidence[0]["snippet"]) == common.MAX_SNIPPET_CHARS


def test_format_answer_requires_two_sources() -> None:
    common = load_common()

    assert (
        common.format_answer("The answer.", ["https://example.com/1"])
        == common.ABSTENTION_MESSAGE
    )


def test_format_answer_appends_at_most_three_sources() -> None:
    common = load_common()
    answer = common.format_answer(
        "The answer.",
        [
            "https://example.com/1",
            "https://example.com/2",
            "https://example.com/3",
            "https://example.com/4",
        ],
    )

    assert answer == (
        "The answer.\n\nSources:\n"
        "- https://example.com/1\n"
        "- https://example.com/2\n"
        "- https://example.com/3"
    )


def test_validate_grounded_answer_rejects_invented_source() -> None:
    common = load_common()
    answer = (
        "The answer.\n\nSources:\n"
        "- https://example.com/1\n"
        "- https://invented.example/result"
    )

    assert not common.validate_grounded_answer(
        answer,
        {"https://example.com/1", "https://example.com/2"},
    )
