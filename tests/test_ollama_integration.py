import asyncio
from pathlib import Path
from typing import Any

import pytest

from mnemo8.chat import ConversationEngine
from mnemo8.commands import init_workspace
from mnemo8.loader import load_agents, load_skills
from mnemo8.models import RuntimeState

INTEGRATION_MODEL = "llama3.1:8b"
DETERMINISTIC_OPTIONS = {
    "seed": 42,
    "temperature": 0,
}


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
def ollama_llama31_available():
    ollama = pytest.importorskip("ollama")
    try:
        response = ollama.list()
    except Exception as exc:
        pytest.skip(f"Ollama is not reachable: {exc}")

    model_names = _ollama_model_names(response)
    if INTEGRATION_MODEL not in model_names:
        pytest.skip(f"Ollama model {INTEGRATION_MODEL!r} is not installed")


@pytest.fixture
def dori_runtime(tmp_path, monkeypatch, ollama_llama31_available):
    monkeypatch.setenv("HOME", str(tmp_path))
    init_workspace(str(Path.cwd()))

    return RuntimeState(
        cwd=str(tmp_path),
        agents_content=load_agents(),
        skills=load_skills(),
        model=INTEGRATION_MODEL,
        ollama_options=DETERMINISTIC_OPTIONS,
        skill_confidence_threshold=0.8,
    )


@pytest.mark.integration
def test_llama31_answers_without_skill_when_no_skill_matches(dori_runtime):
    engine = ConversationEngine(dori_runtime)

    response = asyncio.run(
        engine.send("No skill is needed. Reply with exactly this token: DORI_OK")
    )

    assert response.resolved_skill is None
    assert response.skill_output is None
    assert "DORI_OK" in response.display_text


@pytest.mark.integration
def test_llama31_routes_reminder_skill_and_runs_script(dori_runtime):
    engine = ConversationEngine(dori_runtime)

    response = asyncio.run(engine.send("Remind me to drink water tomorrow at 9am."))

    assert response.resolved_skill is not None
    assert response.resolved_skill["skill"] == "reminders"
    assert response.skill_output is not None
    assert "[System]: I have scheduled a reminder" in response.skill_output
    assert "drink water" in response.skill_output.lower()
    assert "9" in response.skill_output
    assert "✓ reminders" in response.display_text


@pytest.mark.integration
def test_llama31_routes_devtools_git_skill_through_router(dori_runtime):
    engine = ConversationEngine(dori_runtime)

    response = asyncio.run(engine.send("How do I delete a git tag from local only?"))

    assert response.resolved_skill is not None
    assert response.resolved_skill["skill"] == "git"
    assert response.skill_output is not None
    assert "Delete a tag" in response.skill_output
    assert "git tag -d <tag-name>" in response.skill_output
    assert "✓ git" in response.display_text
