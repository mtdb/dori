# Legacy Pipeline Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the legacy routing pipeline's best patterns (structured skill prompts, cross-turn slot memory, entity repair with dateparser, clarification flow) into the lightweight CLI while keeping `skills/*.md` + `scripts/*.py` unchanged.

**Architecture:** A thin pipeline layer is added to `chat.py` between JSON parse and subprocess dispatch: merge entities into session-scoped `resolved_entities`, run skill-specific repair, check required fields, ask for clarification if needed, dispatch when complete. All state is in-memory; no persistence added.

**Tech Stack:** Python 3.11+, `dateparser>=1.1.0`, `pytest>=8.0` (dev), `rich`, `ollama`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `mnemo8/models.py` | Modify | Add `resolved_entities` and `pending_intent` to `RuntimeState` |
| `mnemo8/repair.py` | Create | `repair()` dispatcher + `_repair_reminders()` using dateparser |
| `mnemo8/chat.py` | Modify | Structured prompt, helper functions, pipeline in REPL loop |
| `pyproject.toml` | Modify | Add `dateparser>=1.1.0`, `pytest>=8.0` dev dep |
| `tests/test_models.py` | Create | Unit tests for new `RuntimeState` fields |
| `tests/test_repair.py` | Create | Unit tests for `repair()` and `_repair_reminders()` |
| `tests/test_chat.py` | Create | Unit tests for `_merge_entities`, `_missing_fields`, `_clarification_message`, `build_system_prompt` |

---

## Task 1: Add session state fields to RuntimeState

**Files:**
- Modify: `mnemo8/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Create tests/test_models.py with failing tests**

```python
from mnemo8.models import RuntimeState


def test_runtime_state_has_resolved_entities():
    state = RuntimeState(cwd="/tmp")
    assert state.resolved_entities == {}


def test_runtime_state_has_pending_intent():
    state = RuntimeState(cwd="/tmp")
    assert state.pending_intent is None


def test_runtime_state_resolved_entities_is_mutable():
    state = RuntimeState(cwd="/tmp")
    state.resolved_entities["reminders"] = {"message": "buy milk"}
    assert state.resolved_entities["reminders"]["message"] == "buy milk"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/mauricio/opt/mnemo8 && pytest tests/test_models.py -v
```

Expected: `AttributeError` — `resolved_entities` not defined on `RuntimeState`.

- [ ] **Step 3: Update mnemo8/models.py**

Replace the entire file with:

```python
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Skill:
    name: str
    path: str
    content: str


@dataclass
class RuntimeState:
    cwd: str
    agents_content: Optional[str] = None
    skills: List[Skill] = field(default_factory=list)
    chat_history: List[str] = field(default_factory=list)
    resolved_entities: dict = field(default_factory=dict)
    pending_intent: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mnemo8/models.py tests/test_models.py
git commit -m "feat: add resolved_entities and pending_intent to RuntimeState"
```

---

## Task 2: Add dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update pyproject.toml**

Replace the entire file with:

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "mnemo8"
version = "0.1.0"
description = "mnemo8 MVP Terminal Assistant"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "rich>=13.0.0",
    "ollama>=0.2.0",
    "dateparser>=1.1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
mnemo8 = "mnemo8.main:run"

[tool.setuptools]
packages = ["mnemo8"]
```

- [ ] **Step 2: Install all dependencies**

```bash
pip install -e ".[dev]"
```

Expected: `dateparser` and `pytest` appear in the install summary.

- [ ] **Step 3: Verify dateparser works**

```bash
python -c "import dateparser; print(dateparser.parse('tomorrow at 9am', settings={'PREFER_DATES_FROM': 'future'}))"
```

Expected: prints a future datetime object (not `None`).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add dateparser and pytest dependencies"
```

---

## Task 3: Create mnemo8/repair.py with TDD

**Files:**
- Create: `mnemo8/repair.py`
- Create: `tests/test_repair.py`

- [ ] **Step 1: Create tests/test_repair.py with failing tests**

```python
import pytest
from datetime import datetime, timezone
from mnemo8.repair import repair, _repair_reminders


def test_repair_unknown_skill_returns_entities_unchanged():
    entities = {"skill": "unknown", "foo": "bar"}
    assert repair("unknown", entities) == entities


def test_repair_reminders_strips_filler_from_message():
    entities = {
        "skill": "reminders",
        "message": "remind me to buy milk",
        "when": "tomorrow at 9am",
    }
    result = repair("reminders", entities)
    assert result["message"] == "buy milk"


def test_repair_reminders_strips_spanish_filler():
    entities = {
        "skill": "reminders",
        "message": "recuérdame comprar leche",
        "when": "mañana a las 9am",
        "raw_text": "recuérdame comprar leche mañana a las 9am",
    }
    result = repair("reminders", entities)
    assert "recuérdame" not in result["message"]


def test_repair_reminders_normalizes_when_to_iso():
    entities = {
        "skill": "reminders",
        "message": "buy milk",
        "when": "tomorrow at 9am",
        "raw_text": "remind me to buy milk tomorrow at 9am",
    }
    result = repair("reminders", entities)
    dt = datetime.fromisoformat(result["when"])
    assert dt > datetime.now(tz=dt.tzinfo or timezone.utc)


def test_repair_reminders_removes_time_phrase_from_message():
    entities = {
        "skill": "reminders",
        "message": "buy milk tomorrow at 9am",
        "when": "tomorrow at 9am",
        "raw_text": "remind me to buy milk tomorrow at 9am",
    }
    result = repair("reminders", entities)
    assert "tomorrow" not in result["message"]
    assert "9am" not in result["message"]


def test_repair_reminders_raises_on_unparseable_time():
    entities = {
        "skill": "reminders",
        "message": "do something",
        "raw_text": "do something xyzzy",
    }
    entities.pop("when", None)
    with pytest.raises(ValueError, match="Could not parse"):
        repair("reminders", entities)


def test_repair_does_not_mutate_input():
    original = {"skill": "reminders", "message": "remind me to call mom", "when": "tomorrow at 9am"}
    repair("reminders", original)
    assert original["message"] == "remind me to call mom"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_repair.py -v
```

Expected: `ModuleNotFoundError: No module named 'mnemo8.repair'`

- [ ] **Step 3: Create mnemo8/repair.py**

```python
import re
from datetime import datetime, timezone

import dateparser

_REMINDER_FILLER_RE = re.compile(
    r"\b(remind me to|recuérdame( que)?|please|set an? reminder to|set an? alarm to)\b\s*",
    re.IGNORECASE,
)


def repair(skill_name: str, entities: dict) -> dict:
    if skill_name == "reminders":
        return _repair_reminders(entities)
    return entities


def _repair_reminders(entities: dict) -> dict:
    entities = dict(entities)

    if "message" in entities:
        entities["message"] = _REMINDER_FILLER_RE.sub("", entities["message"]).strip()

    raw = entities.get("raw_text") or entities.get("when", "")
    results = dateparser.search_dates(
        raw,
        settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": True},
    )

    if results:
        phrase, dt = results[0]
        if dt <= datetime.now(tz=timezone.utc):
            raise ValueError("Scheduled time is in the past")
        entities["when"] = dt.isoformat()
        if "message" in entities:
            entities["message"] = entities["message"].replace(phrase, "").strip()
    elif not entities.get("when"):
        raise ValueError("Could not parse a time expression from the input")

    return entities
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_repair.py -v
```

Expected: all 7 tests PASS. (The past-time test may depend on your local clock — if `tomorrow at 9am` is in the past adjust the test input.)

- [ ] **Step 5: Commit**

```bash
git add mnemo8/repair.py tests/test_repair.py
git commit -m "feat: add repair.py with reminder entity repair using dateparser"
```

---

## Task 4: Improve build_system_prompt and extract chat helpers

**Files:**
- Modify: `mnemo8/chat.py`
- Create: `tests/test_chat.py`

- [ ] **Step 1: Create tests/test_chat.py with failing tests**

```python
from mnemo8.models import RuntimeState, Skill
from mnemo8.chat import (
    _merge_entities,
    _missing_fields,
    _clarification_message,
    build_system_prompt,
)


def test_merge_entities_combines_existing_and_new():
    resolved = {"reminders": {"message": "call Juan"}}
    result = _merge_entities(resolved, "reminders", {"when": "tomorrow at 9"})
    assert result == {"message": "call Juan", "when": "tomorrow at 9"}


def test_merge_entities_new_values_win():
    resolved = {"reminders": {"message": "old message"}}
    result = _merge_entities(resolved, "reminders", {"message": "new message"})
    assert result["message"] == "new message"


def test_merge_entities_empty_resolved():
    result = _merge_entities({}, "reminders", {"message": "buy milk"})
    assert result == {"message": "buy milk"}


def test_missing_fields_all_present():
    entities = {"skill": "reminders", "message": "buy milk", "when": "2026-04-28T22:00:00+00:00"}
    assert _missing_fields("reminders", entities) == []


def test_missing_fields_detects_missing_when():
    entities = {"skill": "reminders", "message": "buy milk"}
    missing = _missing_fields("reminders", entities)
    assert "when" in missing


def test_missing_fields_detects_missing_message():
    entities = {"skill": "reminders", "when": "2026-04-28T22:00:00+00:00"}
    missing = _missing_fields("reminders", entities)
    assert "message" in missing


def test_missing_fields_unknown_skill_returns_empty():
    assert _missing_fields("unknown", {"foo": "bar"}) == []


def test_clarification_message_missing_when():
    result = _clarification_message("reminders", ["when"])
    assert "time" in result.lower()


def test_clarification_message_missing_message():
    result = _clarification_message("reminders", ["message"])
    assert len(result) > 0


def test_clarification_message_both_missing():
    result = _clarification_message("reminders", ["message", "when"])
    assert len(result) > 0


def test_build_system_prompt_includes_json_schema():
    skill = Skill(name="reminders.md", path="skills/reminders.md", content="# Reminders\nUse for reminders.")
    state = RuntimeState(cwd="/tmp", skills=[skill])
    prompt = build_system_prompt(state)
    assert '"skill": "reminders"' in prompt
    assert "Required fields: skill, message, when" in prompt
    assert "Use for reminders." in prompt


def test_build_system_prompt_no_skills():
    state = RuntimeState(cwd="/tmp")
    prompt = build_system_prompt(state)
    assert "mnemo8" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_chat.py -v
```

Expected: `ImportError` — `_merge_entities`, `_missing_fields`, `_clarification_message` not defined yet.

- [ ] **Step 3: Replace mnemo8/chat.py with the updated version**

Replace the entire file:

```python
import sys
import os
import json
import re
import subprocess
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown

import ollama

from mnemo8.models import RuntimeState
from mnemo8.repair import repair

console = Console()

REQUIRED_FIELDS: dict[str, list[str]] = {
    "reminders": ["message", "when"],
}

_SKILL_SCHEMAS: dict[str, dict[str, str]] = {
    "reminders.md": {
        "json": '{"skill": "reminders", "message": "<task, no time phrases>", "when": "<time expression>", "raw_text": "<original user message>"}',
        "required": "skill, message, when",
        "optional": "raw_text",
    }
}


def _merge_entities(resolved: dict, skill_name: str, new_entities: dict) -> dict:
    existing = resolved.get(skill_name, {})
    return {**existing, **new_entities}


def _missing_fields(skill_name: str, entities: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS.get(skill_name, []) if not entities.get(f)]


def _clarification_message(skill_name: str, missing: list[str]) -> str:
    if skill_name == "reminders":
        if "when" in missing and "message" in missing:
            return "I can set a reminder — what's it for, and when?"
        if "when" in missing:
            return "Got it. What time should I set the reminder for?"
        if "message" in missing:
            return "Sure! What should I remind you about?"
    return f"I need a bit more information: {', '.join(missing)}"


def build_system_prompt(state: RuntimeState) -> str:
    prompt = "You are mnemo8, a helpful personal assistant CLI running on the user's terminal.\n"
    if state.agents_content:
        prompt += f"\nHere is information about available agents that might be relevant:\n{state.agents_content}\n"
    if state.skills:
        prompt += "\nAvailable skills — if the user's intent matches a skill, output ONLY valid JSON with the schema shown. Otherwise respond in plain text.\n"
        for skill in state.skills:
            schema = _SKILL_SCHEMAS.get(skill.name)
            prompt += f"\n--- Skill: {skill.name} ---\n"
            if schema:
                prompt += f"Output ONLY this JSON when matched:\n{schema['json']}\n"
                prompt += f"Required fields: {schema['required']}\n"
                if schema.get("optional"):
                    prompt += f"Optional fields: {schema['optional']}\n"
            prompt += f"\n{skill.content}\n---\n"
    return prompt


def start_chat(state: RuntimeState):
    """Start the REPL chat loop."""
    console.print(f"\n[bold cyan]mnemo8 Personal Assistant[/bold cyan]")
    console.print(f"Directory: [green]{state.cwd}[/green]")

    if state.agents_content is not None:
        console.print("AGENTS.md [green]loaded[/green]")
    else:
        console.print("AGENTS.md [yellow]not found[/yellow]")

    console.print(f"Skills loaded: [green]{len(state.skills)}[/green]\n")

    system_prompt = build_system_prompt(state)
    messages = [{"role": "system", "content": system_prompt}]

    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]")

            if user_input.strip().lower() in ["exit", "quit"]:
                console.print("\n[yellow]Exiting mnemo8...[/yellow]")
                break

            if not user_input.strip():
                continue

            messages.append({"role": "user", "content": user_input})

            with console.status("[bold cyan]Thinking...[/bold cyan]"):
                response = ollama.chat(model="llama3.1:8b", messages=messages)

            assistant_content = response["message"]["content"]
            messages.append({"role": "assistant", "content": assistant_content})

            console.print("\n[bold cyan]mnemo8[/bold cyan] >")

            parsed_json = None
            try:
                parsed_json = json.loads(assistant_content)
            except json.JSONDecodeError:
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", assistant_content, re.DOTALL)
                if match:
                    try:
                        parsed_json = json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass

            if parsed_json and isinstance(parsed_json, dict) and "skill" in parsed_json:
                skill_name = parsed_json["skill"]

                merged = _merge_entities(state.resolved_entities, skill_name, parsed_json)
                state.resolved_entities[skill_name] = merged

                try:
                    merged = repair(skill_name, merged)
                    state.resolved_entities[skill_name] = merged
                except ValueError as e:
                    console.print(f"[red]{e}[/red]")
                    console.print()
                    continue

                missing = _missing_fields(skill_name, merged)
                if missing:
                    state.pending_intent = skill_name
                    console.print(_clarification_message(skill_name, missing))
                else:
                    script_path = os.path.join(state.cwd, "scripts", f"{skill_name}.py")
                    if os.path.isfile(script_path):
                        try:
                            result = subprocess.run(
                                [sys.executable, script_path, json.dumps(merged)],
                                capture_output=True,
                                text=True,
                                check=True,
                            )
                            console.print(f"[bold green]Skill Executed:[/bold green] {skill_name}")
                            console.print(result.stdout.strip())
                        except subprocess.CalledProcessError as e:
                            console.print(f"[red]Skill script '{skill_name}' failed:[/red]\n{e.stderr.strip()}")
                    else:
                        console.print(f"[red]Error:[/red] No script found for skill '{skill_name}'")
                    state.resolved_entities.pop(skill_name, None)
                    state.pending_intent = None
            else:
                state.pending_intent = None
                console.print(Markdown(assistant_content))

            console.print()

        except (KeyboardInterrupt, EOFError):
            console.print("\n\n[yellow]Exiting mnemo8...[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]An error occurred: {e}[/red]")
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS including the new `test_chat.py` suite.

- [ ] **Step 5: Commit**

```bash
git add mnemo8/chat.py tests/test_chat.py
git commit -m "feat: structured skill prompts, entity pipeline, and clarification flow in chat.py"
```

---

## Task 5: Smoke test end-to-end

No code changes. Verify the full pipeline works with a live Ollama session.

- [ ] **Step 1: Ensure Ollama is running with the right model**

```bash
ollama list
```

Expected: `llama3.1:8b` appears in the list. If not: `ollama pull llama3.1:8b`

- [ ] **Step 2: Run mnemo8 from the repo root (which has skills/ and scripts/)**

```bash
cd /home/mauricio/opt/mnemo8 && mnemo8
```

Expected startup output:
```
mnemo8 Personal Assistant
Directory: /home/mauricio/opt/mnemo8
AGENTS.md not found
Skills loaded: 1
```

- [ ] **Step 3: Test single-turn reminder (all fields provided)**

Type: `Remind me to call Juan tomorrow at 9am`

Expected: LLM returns JSON → repair strips filler and normalizes `when` to ISO → script executes:
```
Skill Executed: reminders
⏰ [System]: I have scheduled a reminder for 'call Juan' at '2026-04-29T09:00:00+00:00'.
```

- [ ] **Step 4: Test two-turn slot filling**

Turn 1 — type: `Remind me to buy milk`

Expected: mnemo8 asks `Got it. What time should I set the reminder for?`

Turn 2 — type: `Tomorrow at 6pm`

Expected: skill executes with `message=buy milk` and normalized `when`.

- [ ] **Step 5: Test plain text response**

Type: `What is the capital of France?`

Expected: LLM responds in plain text (Markdown rendered), no skill dispatch.

- [ ] **Step 6: Run full test suite one last time**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "test: confirm end-to-end pipeline smoke test passes"
```
