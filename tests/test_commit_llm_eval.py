"""LLM evaluation for commit message generation.

Runs the real local model (llama3.1:8b, seed 42, temperature 0) against a
corpus of real commits from angular/angular and this repository, stored in
tests/fixtures/commit_corpus/. See the corpus README for how cases are
curated and regenerated.

A generated message passes when:
- it survives the script's own validation,
- its type is one of the curated acceptable types,
- every expected keyword group matches (at least one alternative per group,
  case-insensitive substring over subject and body).

The conventional-commit scope is intentionally NOT asserted: project scopes
(`core`, `docs-infra`, ...) are internal conventions a model cannot infer
from a diff alone.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "commit_corpus"
WORKFLOW = ROOT / "boilerplate" / "scripts" / "_commit_workflow.py"

spec = importlib.util.spec_from_file_location("dori_commit_workflow_eval", WORKFLOW)
assert spec is not None
assert spec.loader is not None
commit_workflow = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = commit_workflow
spec.loader.exec_module(commit_workflow)

INTEGRATION_MODEL = commit_workflow.COMMIT_MESSAGE_MODEL
DETERMINISTIC_OPTIONS = {"seed": 42, "temperature": 0}
SUBJECT_RE = re.compile(r"^(\w+)(?:\(([^)]+)\))?!?:\s+(.+)$")

CASES = sorted(CORPUS.glob("*.json"))


def _ollama_model_names(response: Any) -> set[str]:
    models = getattr(response, "models", None)
    if models is None and isinstance(response, dict):
        models = response.get("models", [])

    names: set[str] = set()
    for model in models or []:
        name = getattr(model, "model", None) or getattr(model, "name", None)
        if name is None and isinstance(model, dict):
            name = model.get("model") or model.get("name")
        if name:
            names.add(name)
    return names


@pytest.fixture(scope="session")
def ollama_model_available():
    ollama = pytest.importorskip("ollama")
    try:
        response = ollama.list()
    except Exception as exc:
        pytest.skip(f"Ollama is not reachable: {exc}")

    if INTEGRATION_MODEL not in _ollama_model_names(response):
        pytest.skip(f"Ollama model {INTEGRATION_MODEL!r} is not installed")


@pytest.fixture(autouse=True)
def deterministic_options(monkeypatch):
    monkeypatch.setattr(
        commit_workflow, "COMMIT_MESSAGE_OPTIONS", DETERMINISTIC_OPTIONS
    )
    monkeypatch.setattr(
        commit_workflow,
        "COMMIT_MESSAGE_RETRY_OPTIONS",
        {"seed": 42, "temperature": 0.6},
    )


def _build_request(fixture: dict) -> "commit_workflow.CommitRequest":
    files = [
        commit_workflow.ChangedFile(path=f["path"], status=f["status"])
        for f in fixture["files"]
    ]
    changes = commit_workflow.StagedChanges(
        files=files,
        stat=fixture["stat"],
        diff=commit_workflow.truncate_diff(
            fixture["diff"], commit_workflow.MAX_PROMPT_DIFF_CHARS
        ),
        recent_subjects=tuple(fixture["recent_subjects"]),
    )
    return commit_workflow.CommitRequest(
        changes=changes,
        commit_type=commit_workflow.detect_type_from_paths(files),
    )


@pytest.mark.integration
@pytest.mark.parametrize("fixture_path", CASES, ids=[path.stem for path in CASES])
def test_generated_commit_message_is_good_enough(fixture_path, ollama_model_available):
    fixture = json.loads(fixture_path.read_text())
    reference = fixture.get("curated_subject") or fixture["original_subject"]

    message = commit_workflow.suggest_commit_message(_build_request(fixture))

    assert message is not None, (
        f"no valid message generated: {commit_workflow._last_ollama_error}\n"
        f"reference: {reference}"
    )

    subject = message.splitlines()[0]
    match = SUBJECT_RE.match(subject)
    assert match is not None, f"not conventional: {subject}"

    assert match.group(1) in fixture["expected_types"], (
        f"type {match.group(1)!r} not in {fixture['expected_types']}\n"
        f"generated: {subject}\n"
        f"reference: {reference}"
    )

    haystack = message.lower()
    for group in fixture["expected_keywords"]:
        assert any(alternative.lower() in haystack for alternative in group), (
            f"none of {group} found\ngenerated: {message}\nreference: {reference}"
        )
