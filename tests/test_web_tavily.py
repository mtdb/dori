import importlib.util
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_tavily_module():
    scripts_dir = ROOT / "boilerplate" / "scripts"
    path = ROOT / "boilerplate" / "presets" / "search" / "tavily.py"
    sys.path.insert(0, str(scripts_dir))
    try:
        spec = importlib.util.spec_from_file_location("web_tavily_test", path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts_dir))


def test_build_request_uses_bearer_key_and_native_answer() -> None:
    module = load_tavily_module()

    request = module.build_request("Spain population", "year", "tvly-secret")
    body = json.loads(request.data)

    assert request.full_url == "https://api.tavily.com/search"
    assert request.get_header("Authorization") == "Bearer tvly-secret"
    assert request.get_header("Content-type") == "application/json"
    assert body == {
        "query": "Spain population",
        "search_depth": "basic",
        "include_answer": "basic",
        "max_results": 5,
        "time_range": "year",
    }


def test_answer_payload_formats_native_answer_with_returned_sources(
    monkeypatch,
) -> None:
    module = load_tavily_module()
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret")
    monkeypatch.setattr(
        module,
        "search",
        lambda query, freshness, api_key: {
            "answer": "Spain has an estimated population of 49 million.",
            "results": [
                {
                    "title": "INE",
                    "url": "https://ine.example/population",
                    "content": "Official estimate.",
                },
                {
                    "title": "World Bank",
                    "url": "https://worldbank.example/spain",
                    "content": "Population data.",
                },
            ],
        },
    )

    answer = module.answer_payload({"query": "Spain population"})

    assert answer == (
        "Spain has an estimated population of 49 million.\n\n"
        "Sources:\n"
        "- https://ine.example/population\n"
        "- https://worldbank.example/spain"
    )


def test_answer_payload_requires_api_key(monkeypatch) -> None:
    module = load_tavily_module()
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    with pytest.raises(module.WebSearchError, match="TAVILY_API_KEY"):
        module.answer_payload({"query": "Spain population"})


def test_answer_payload_abstains_without_two_sources(monkeypatch) -> None:
    module = load_tavily_module()
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret")
    monkeypatch.setattr(
        module,
        "search",
        lambda query, freshness, api_key: {
            "answer": "An answer.",
            "results": [{"title": "One", "url": "https://example.com/1"}],
        },
    )

    assert module.answer_payload({"query": "question"}) == module.ABSTENTION_MESSAGE


def test_search_parses_successful_json_response(monkeypatch) -> None:
    module = load_tavily_module()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"answer": "ok", "results": []}).encode("utf-8")

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: FakeResponse())

    payload = module.search("question", None, "tvly-secret")

    assert payload == {"answer": "ok", "results": []}


def test_search_wraps_authentication_failure(monkeypatch) -> None:
    module = load_tavily_module()
    request = module.build_request("question", None, "tvly-secret")
    error = HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)
    monkeypatch.setattr(
        module, "urlopen", lambda request, timeout: (_ for _ in ()).throw(error)
    )

    with pytest.raises(module.WebSearchError, match="Tavily rejected TAVILY_API_KEY"):
        module.search("question", None, "tvly-secret")


def test_search_wraps_rate_limit_failure(monkeypatch) -> None:
    module = load_tavily_module()
    request = module.build_request("question", None, "tvly-secret")
    error = HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=None)
    monkeypatch.setattr(
        module, "urlopen", lambda request, timeout: (_ for _ in ()).throw(error)
    )

    with pytest.raises(module.WebSearchError, match="rate limit"):
        module.search("question", None, "tvly-secret")


def test_search_wraps_network_failure(monkeypatch) -> None:
    module = load_tavily_module()
    monkeypatch.setattr(
        module,
        "urlopen",
        lambda request, timeout: (_ for _ in ()).throw(URLError("offline")),
    )

    with pytest.raises(module.WebSearchError, match="Could not connect to Tavily"):
        module.search("question", None, "tvly-secret")


def test_search_wraps_malformed_json(monkeypatch) -> None:
    module = load_tavily_module()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"not-json"

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(module.WebSearchError, match="invalid response"):
        module.search("question", None, "tvly-secret")
