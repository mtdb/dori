import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_ddgs_module():
    scripts_dir = ROOT / "boilerplate" / "scripts"
    path = ROOT / "boilerplate" / "presets" / "search" / "ddgs.py"
    sys.path.insert(0, str(scripts_dir))
    try:
        spec = importlib.util.spec_from_file_location("web_ddgs_test", path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts_dir))


def test_ddgs_search_maps_freshness_and_normalizes_results(monkeypatch) -> None:
    module = load_ddgs_module()
    calls = []

    class FakeDDGS:
        def text(self, query, **kwargs):
            calls.append((query, kwargs))
            return [
                {
                    "title": "Nintendo",
                    "href": "https://nintendo.example/switch-2",
                    "body": "Released June 5, 2025.",
                },
                {
                    "title": "Reuters",
                    "href": "https://reuters.example/switch-2",
                    "body": "The console launched June 5.",
                },
            ]

    monkeypatch.setattr(module, "_load_ddgs", lambda: FakeDDGS())

    evidence = module.retrieve_evidence("Switch 2 release", "month")

    assert calls == [("Switch 2 release", {"max_results": 5, "timelimit": "m"})]
    assert evidence[0]["url"] == "https://nintendo.example/switch-2"


def test_build_messages_constrains_model_to_evidence() -> None:
    module = load_ddgs_module()
    messages = module.build_messages(
        "When was Switch 2 released?",
        [
            {
                "title": "Nintendo",
                "url": "https://nintendo.example/switch-2",
                "snippet": "Released June 5, 2025.",
            },
            {
                "title": "Reuters",
                "url": "https://reuters.example/switch-2",
                "snippet": "Launched June 5.",
            },
        ],
    )

    assert "Answer only from the supplied web evidence" in messages[0]["content"]
    assert "Write in English" in messages[0]["content"]
    assert "Untrusted user question" in messages[1]["content"]
    assert "https://nintendo.example/switch-2" in messages[1]["content"]


def test_answer_payload_returns_valid_grounded_answer(monkeypatch) -> None:
    module = load_ddgs_module()
    evidence = [
        {
            "title": "Nintendo",
            "url": "https://nintendo.example/switch-2",
            "snippet": "Released June 5, 2025.",
        },
        {
            "title": "Reuters",
            "url": "https://reuters.example/switch-2",
            "snippet": "Launched June 5.",
        },
    ]
    monkeypatch.setattr(module, "retrieve_evidence", lambda query, freshness: evidence)
    monkeypatch.setattr(
        module,
        "generate_answer",
        lambda query, evidence: (
            "The Nintendo Switch 2 was released on June 5, 2025.\n\n"
            "Sources:\n"
            "- https://nintendo.example/switch-2\n"
            "- https://reuters.example/switch-2"
        ),
    )

    answer = module.answer_payload(
        {
            "query": "Switch 2 release date",
            "raw_text": "When was Switch 2 released?",
        }
    )

    assert answer.startswith("The Nintendo Switch 2 was released")


def test_answer_payload_abstains_for_invalid_model_citation(monkeypatch) -> None:
    module = load_ddgs_module()
    evidence = [
        {"title": "One", "url": "https://example.com/1", "snippet": "one"},
        {"title": "Two", "url": "https://example.com/2", "snippet": "two"},
    ]
    monkeypatch.setattr(module, "retrieve_evidence", lambda query, freshness: evidence)
    monkeypatch.setattr(
        module,
        "generate_answer",
        lambda query, evidence: (
            "Unsupported answer.\n\nSources:\n"
            "- https://invented.example/1\n"
            "- https://invented.example/2"
        ),
    )

    assert module.answer_payload({"query": "question"}) == module.ABSTENTION_MESSAGE


def test_answer_payload_abstains_with_fewer_than_two_evidence_records(
    monkeypatch,
) -> None:
    module = load_ddgs_module()
    monkeypatch.setattr(
        module,
        "retrieve_evidence",
        lambda query, freshness: [
            {"title": "One", "url": "https://example.com/1", "snippet": "one"}
        ],
    )

    assert module.answer_payload({"query": "question"}) == module.ABSTENTION_MESSAGE


def test_generate_answer_uses_dori_web_model_override(monkeypatch) -> None:
    module = load_ddgs_module()
    monkeypatch.setenv("DORI_WEB_MODEL", "qwen:test")
    seen = {}

    class FakeOllama:
        @staticmethod
        def chat(*, model, messages, options):
            seen["model"] = model
            seen["messages"] = messages
            seen["options"] = options
            return {
                "message": {
                    "content": "Answer\n\nSources:\n- https://example.com/1\n- https://example.com/2"
                }
            }

    monkeypatch.setattr(module, "_load_ollama", lambda: FakeOllama)

    module.generate_answer(
        "question",
        [
            {"title": "One", "url": "https://example.com/1", "snippet": "one"},
            {"title": "Two", "url": "https://example.com/2", "snippet": "two"},
        ],
    )

    assert seen["model"] == "qwen:test"
    assert seen["options"] == {"temperature": 0}


def test_import_module_without_script_dir_avoids_stdlib_shadowing(
    monkeypatch, tmp_path
) -> None:
    module = load_ddgs_module()
    script_dir = tmp_path / "scripts"
    library_dir = tmp_path / "lib"
    script_dir.mkdir()
    library_dir.mkdir()

    (script_dir / "calendar.py").write_text("BROKEN = True\n", encoding="utf-8")
    (library_dir / "targetpkg.py").write_text(
        "from calendar import timegm\n"
        "VALUE = timegm((1970, 1, 1, 0, 0, 0, 0, 1, -1))\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "__file__", str(script_dir / "web.py"))
    monkeypatch.setattr(sys, "path", [str(script_dir), str(library_dir), *sys.path])
    sys.modules.pop("calendar", None)
    sys.modules.pop("targetpkg", None)

    imported = module._import_module_without_script_dir("targetpkg")

    assert imported.VALUE == 0


def test_load_ddgs_instantiates_without_script_dir_shadowing(
    monkeypatch, tmp_path
) -> None:
    module = load_ddgs_module()
    script_dir = tmp_path / "scripts"
    library_dir = tmp_path / "lib"
    ddgs_pkg = library_dir / "ddgs"
    script_dir.mkdir()
    ddgs_pkg.mkdir(parents=True)

    (script_dir / "calendar.py").write_text("BROKEN = True\n", encoding="utf-8")
    (ddgs_pkg / "__init__.py").write_text(
        "class DDGS:\n"
        "    def __init__(self):\n"
        "        from calendar import timegm\n"
        "        self.value = timegm((1970, 1, 1, 0, 0, 0, 0, 1, -1))\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "__file__", str(script_dir / "web.py"))
    monkeypatch.setattr(sys, "path", [str(script_dir), str(library_dir), *sys.path])
    sys.modules.pop("calendar", None)
    sys.modules.pop("ddgs", None)

    client = module._load_ddgs()

    assert client.value == 0


def test_retrieve_evidence_wraps_ddgs_failures(monkeypatch) -> None:
    module = load_ddgs_module()

    class FakeDDGS:
        def text(self, query, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(module, "_load_ddgs", lambda: FakeDDGS)

    with pytest.raises(module.WebSearchError, match="DDGS search failed"):
        module.retrieve_evidence("question", None)


def test_generate_answer_wraps_ollama_failures(monkeypatch) -> None:
    module = load_ddgs_module()

    class FakeOllama:
        @staticmethod
        def chat(*, model, messages, options):
            raise RuntimeError("boom")

    monkeypatch.setattr(module, "_load_ollama", lambda: FakeOllama)

    with pytest.raises(
        module.WebSearchError,
        match="Ollama could not generate the web answer",
    ):
        module.generate_answer(
            "question",
            [
                {"title": "One", "url": "https://example.com/1", "snippet": "one"},
                {"title": "Two", "url": "https://example.com/2", "snippet": "two"},
            ],
        )
