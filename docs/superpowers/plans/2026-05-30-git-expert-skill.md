# Git Expert Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the brittle Git lookup skill with a read-only Git expert skill that answers from local Git documentation and abstains when evidence is insufficient.

**Architecture:** Keep the existing Dori skill/script contract. `boilerplate/scripts/git.py` becomes a small local-documentation retrieval and LLM-answering pipeline, while `boilerplate/skills/devtools/git.md` documents the expert behavior for routing and extraction. Tests cover pure helper behavior first, then script orchestration and skill boilerplate.

**Tech Stack:** Python 3.11, pytest, stdlib subprocess, stdlib importlib test loading, existing `ollama` package dependency.

---

## File Structure

- Modify `boilerplate/scripts/git.py`: replace the hardcoded answer table with pure helpers for topic normalization, safe local documentation command construction, retrieval, prompt building, LLM generation, abstention, and CLI output.
- Modify `boilerplate/skills/devtools/git.md`: describe the Git Expert Skill in English with evidence-only behavior and routing examples.
- Modify `tests/test_boilerplate.py`: assert the Git skill remains under `devtools`, is English, documents expert behavior, and includes required payload fields in examples.
- Create `tests/test_git_expert_script.py`: unit-test the script by loading `boilerplate/scripts/git.py` with `importlib.util.spec_from_file_location`, avoiding package layout changes.
- No changes to `mnemo8/chat.py` or `mnemo8/schemas.py`: the existing `topic`, `context`, and `raw_text` payload contract is sufficient for v1.

---

### Task 1: Add Pure Topic Normalization Tests

**Files:**
- Create: `tests/test_git_expert_script.py`
- Modify: `boilerplate/scripts/git.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_git_expert_script.py`:

```python
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GIT_SCRIPT = ROOT / "boilerplate" / "scripts" / "git.py"


def load_git_script():
    spec = importlib.util.spec_from_file_location("dori_git_script", GIT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_normalize_topic_maps_common_phrasings_to_git_commands():
    git_script = load_git_script()

    cases = {
        "how do I squash the last three commits": "rebase",
        "delete a remote branch": "branch",
        "what is git cherry pick": "cherry-pick",
        "undo a commit safely": "revert",
        "show changes before committing": "diff",
        "move work to another branch with stash": "stash",
    }

    for raw_topic, expected in cases.items():
        assert git_script.normalize_topic(raw_topic) == expected


def test_normalize_topic_returns_none_for_unknown_topics():
    git_script = load_git_script()

    assert git_script.normalize_topic("configure my editor theme") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py -v
```

Expected: FAIL with `AttributeError: module 'dori_git_script' has no attribute 'normalize_topic'`.

- [ ] **Step 3: Add the minimal normalization implementation**

In `boilerplate/scripts/git.py`, replace the existing hardcoded table implementation with this initial skeleton:

```python
import json
import re
import sys


ABSTENTION_MESSAGE = "🌿 [Git]: I could not find enough local documentation to answer safely."

SUPPORTED_COMMANDS = {
    "cherry-pick",
    "rebase",
    "stash",
    "branch",
    "tag",
    "remote",
    "reset",
    "revert",
    "merge",
    "log",
    "diff",
    "status",
    "commit",
    "checkout",
    "switch",
    "restore",
}

PHRASE_COMMANDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("squash", "commit"), "rebase"),
    (("interactive", "rebase"), "rebase"),
    (("cherry", "pick"), "cherry-pick"),
    (("cherry-pick",), "cherry-pick"),
    (("delete", "branch"), "branch"),
    (("remove", "branch"), "branch"),
    (("remote", "branch"), "branch"),
    (("delete", "tag"), "tag"),
    (("remove", "tag"), "tag"),
    (("undo", "commit", "safely"), "revert"),
    (("undo", "commit"), "revert"),
    (("reset", "revert"), "revert"),
    (("show", "changes"), "diff"),
    (("changes", "before", "commit"), "diff"),
    (("move", "work"), "stash"),
)


def _tokens(text: str) -> set[str]:
    normalized = text.lower().replace("_", "-")
    return set(re.findall(r"[a-z0-9-]+", normalized))


def normalize_topic(topic: str) -> str | None:
    words = _tokens(topic)
    if not words:
        return None

    for command in SUPPORTED_COMMANDS:
        if command in words:
            return command

    for required_words, command in PHRASE_COMMANDS:
        if all(word in words for word in required_words):
            return command

    return None
```

Keep the existing `main()` temporarily if needed, but remove references to deleted globals such as `GIT_ANSWERS` once later tasks replace the CLI flow.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py -v
```

Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_git_expert_script.py boilerplate/scripts/git.py
git commit -m "refactor(git): ♻️ add git expert topic normalization"
```

---

### Task 2: Add Safe Local Documentation Retrieval

**Files:**
- Modify: `tests/test_git_expert_script.py`
- Modify: `boilerplate/scripts/git.py`

- [ ] **Step 1: Write the failing tests**

Append these tests to `tests/test_git_expert_script.py`:

```python
from types import SimpleNamespace


def test_retrieve_local_docs_uses_only_read_only_help_commands(monkeypatch):
    git_script = load_git_script()
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, timeout, check):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=0,
            stdout="usage: git rebase [options]\nReplay commits on top of another base tip.",
            stderr="",
        )

    monkeypatch.setattr(git_script.subprocess, "run", fake_run)

    docs = git_script.retrieve_local_docs("rebase")

    assert "Replay commits" in docs
    assert calls == [["git", "help", "rebase"]]


def test_retrieve_local_docs_falls_back_to_short_help_then_man(monkeypatch):
    git_script = load_git_script()
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, timeout, check):
        calls.append(cmd)
        if cmd == ["git", "help", "stash"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="missing")
        if cmd == ["git", "stash", "-h"]:
            return SimpleNamespace(returncode=0, stdout="usage: git stash list", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(git_script.subprocess, "run", fake_run)

    docs = git_script.retrieve_local_docs("stash")

    assert docs == "usage: git stash list"
    assert calls == [["git", "help", "stash"], ["git", "stash", "-h"]]


def test_retrieve_local_docs_returns_none_when_docs_are_missing(monkeypatch):
    git_script = load_git_script()

    def fake_run(cmd, capture_output, text, timeout, check):
        return SimpleNamespace(returncode=1, stdout="", stderr="missing")

    monkeypatch.setattr(git_script.subprocess, "run", fake_run)

    assert git_script.retrieve_local_docs("restore") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py -v
```

Expected: FAIL with `AttributeError: module 'dori_git_script' has no attribute 'retrieve_local_docs'`.

- [ ] **Step 3: Implement retrieval helpers**

Update imports and add retrieval helpers in `boilerplate/scripts/git.py`:

```python
import json
import re
import subprocess
import sys


DOC_TIMEOUT_SECONDS = 3
MAX_DOC_CHARS = 6000


def _run_doc_command(cmd: list[str]) -> str | None:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DOC_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None

    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return None
    return output[:MAX_DOC_CHARS]


def retrieve_local_docs(command: str) -> str | None:
    if command not in SUPPORTED_COMMANDS:
        return None

    commands = [
        ["git", "help", command],
        ["git", command, "-h"],
        ["man", f"git-{command}"],
    ]

    for cmd in commands:
        docs = _run_doc_command(cmd)
        if docs:
            return docs

    return None
```

Keep this retrieval limited to help/man commands. Do not add commands such as `git status`, `git log`, or anything that inspects the user's current repository.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_git_expert_script.py boilerplate/scripts/git.py
git commit -m "feat(git): ✨ retrieve local git documentation"
```

---

### Task 3: Add Evidence-Only Answer Generation

**Files:**
- Modify: `tests/test_git_expert_script.py`
- Modify: `boilerplate/scripts/git.py`

- [ ] **Step 1: Write the failing tests**

Append these tests to `tests/test_git_expert_script.py`:

```python
def test_build_expert_prompt_is_english_only_and_evidence_scoped():
    git_script = load_git_script()

    messages = git_script.build_expert_messages(
        topic="rebase",
        raw_text="How do I squash commits?",
        context="last three commits",
        docs="usage: git rebase [options]",
    )

    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "read-only Git expert" in system_prompt
    assert "Answer only from the provided local Git documentation fragments" in system_prompt
    assert "Do not invent commands" in system_prompt
    assert "last three commits" in user_prompt
    assert "usage: git rebase" in user_prompt


def test_generate_answer_returns_model_content(monkeypatch):
    git_script = load_git_script()

    def fake_chat(model, messages, options):
        return {
            "message": {
                "content": "🌿 [Git - rebase]\nSummary: Rebase replays commits.\nSteps:\n1. Run git rebase."
            }
        }

    monkeypatch.setattr(git_script.ollama, "chat", fake_chat)

    answer = git_script.generate_answer(
        topic="rebase",
        raw_text="How do I rebase?",
        context=None,
        docs="usage: git rebase [options]",
    )

    assert answer.startswith("🌿 [Git - rebase]")


def test_generate_answer_abstains_on_empty_or_unsafe_model_output(monkeypatch):
    git_script = load_git_script()

    def fake_chat(model, messages, options):
        return {"message": {"content": ""}}

    monkeypatch.setattr(git_script.ollama, "chat", fake_chat)

    assert (
        git_script.generate_answer(
            topic="rebase",
            raw_text="How do I rebase?",
            context=None,
            docs="usage: git rebase [options]",
        )
        == git_script.ABSTENTION_MESSAGE
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py -v
```

Expected: FAIL with missing `build_expert_messages` or missing `ollama` import.

- [ ] **Step 3: Implement answer generation**

Add the `ollama` import and generation helpers to `boilerplate/scripts/git.py`:

```python
import ollama


EXPERT_MODEL_OPTIONS = {"temperature": 0}


def build_expert_messages(
    topic: str,
    raw_text: str,
    context: str | None,
    docs: str,
) -> list[dict[str, str]]:
    user_lines = [
        f"User question: {raw_text}",
        f"Normalized topic: {topic}",
    ]
    if context:
        user_lines.append(f"User-provided context: {context}")
    user_lines.append("Local Git documentation fragments:")
    user_lines.append(docs)

    return [
        {
            "role": "system",
            "content": (
                "You are a read-only Git expert.\n"
                "Answer only from the provided local Git documentation fragments.\n"
                "Do not invent commands, flags, effects, or examples.\n"
                "If the fragments are not enough, say that you could not find enough local documentation to answer safely.\n"
                "Do not run Git commands.\n"
                "Do not assume the state of the user's repository.\n"
                "Give safe steps and mention risks only when supported by the documentation.\n"
                "Write in English.\n"
                "Use this format:\n"
                f"🌿 [Git - {topic}]\n"
                "Summary: ...\n"
                "Steps:\n"
                "1. ...\n"
                "Safety notes:\n"
                "- ...\n"
            ),
        },
        {"role": "user", "content": "\n\n".join(user_lines)},
    ]


def _is_usable_answer(answer: str) -> bool:
    if not answer.strip():
        return False
    if "🌿 [Git" not in answer:
        return False
    return True


def generate_answer(
    topic: str,
    raw_text: str,
    context: str | None,
    docs: str,
    model: str = "llama3.1:8b",
) -> str:
    messages = build_expert_messages(topic, raw_text, context, docs)
    try:
        response = ollama.chat(
            model=model,
            messages=messages,
            options=EXPERT_MODEL_OPTIONS,
        )
    except Exception:
        return ABSTENTION_MESSAGE

    answer = response.get("message", {}).get("content", "").strip()
    if not _is_usable_answer(answer):
        return ABSTENTION_MESSAGE
    return answer
```

Use the existing default integration model for now. Do not introduce new config in this task.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_git_expert_script.py boilerplate/scripts/git.py
git commit -m "feat(git): ✨ generate evidence-based git answers"
```

---

### Task 4: Wire The CLI Flow And Abstention Behavior

**Files:**
- Modify: `tests/test_git_expert_script.py`
- Modify: `boilerplate/scripts/git.py`

- [ ] **Step 1: Write the failing tests**

Append these tests to `tests/test_git_expert_script.py`:

```python
def test_answer_payload_abstains_when_topic_is_unknown():
    git_script = load_git_script()

    payload = {
        "skill": "git",
        "confidence": 0.95,
        "topic": "configure my editor theme",
        "raw_text": "How do I configure my editor theme?",
    }

    assert git_script.answer_payload(payload) == git_script.ABSTENTION_MESSAGE


def test_answer_payload_uses_raw_text_when_topic_is_missing(monkeypatch):
    git_script = load_git_script()

    monkeypatch.setattr(git_script, "retrieve_local_docs", lambda command: "usage: git diff")
    monkeypatch.setattr(
        git_script,
        "generate_answer",
        lambda topic, raw_text, context, docs: f"🌿 [Git - {topic}]\nSummary: ok",
    )

    payload = {
        "skill": "git",
        "confidence": 0.95,
        "raw_text": "How do I show changes before committing?",
    }

    assert git_script.answer_payload(payload).startswith("🌿 [Git - diff]")


def test_main_prints_abstention_for_invalid_json(capsys, monkeypatch):
    git_script = load_git_script()

    monkeypatch.setattr("sys.argv", ["git.py", "{not-json"])

    git_script.main()

    assert capsys.readouterr().out.strip() == git_script.ABSTENTION_MESSAGE
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py -v
```

Expected: FAIL with missing `answer_payload` or old CLI behavior.

- [ ] **Step 3: Implement payload orchestration and CLI output**

Replace the old `main()` flow in `boilerplate/scripts/git.py` with:

```python
def answer_payload(payload: dict) -> str:
    topic_text = str(payload.get("topic") or payload.get("raw_text") or "")
    command = normalize_topic(topic_text)
    if command is None:
        return ABSTENTION_MESSAGE

    docs = retrieve_local_docs(command)
    if not docs:
        return ABSTENTION_MESSAGE

    return generate_answer(
        topic=command,
        raw_text=str(payload.get("raw_text") or topic_text),
        context=payload.get("context"),
        docs=docs,
    )


def main():
    if len(sys.argv) < 2:
        print(ABSTENTION_MESSAGE)
        return

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print(ABSTENTION_MESSAGE)
        return

    if not isinstance(payload, dict):
        print(ABSTENTION_MESSAGE)
        return

    print(answer_payload(payload))


if __name__ == "__main__":
    main()
```

Ensure no old `GIT_ANSWERS`, `ALIASES`, `KEYWORD_RULES`, `find_answer`, or `format_answer` code remains.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_git_expert_script.py boilerplate/scripts/git.py
git commit -m "feat(git): ✨ wire git expert skill flow"
```

---

### Task 5: Update The Git Skill Definition

**Files:**
- Modify: `boilerplate/skills/devtools/git.md`
- Modify: `tests/test_boilerplate.py`

- [ ] **Step 1: Write the failing boilerplate tests**

Append these tests to `tests/test_boilerplate.py`:

```python
def test_git_skill_is_read_only_expert_skill() -> None:
    git_skill = ROOT / "boilerplate" / "skills" / "devtools" / "git.md"
    content = git_skill.read_text(encoding="utf-8")

    assert "# Git Expert Skill" in content
    assert "read-only" in content
    assert "local Git documentation" in content
    assert "I could not find enough local documentation to answer safely" in content
    assert "Do not inspect the repository" in content


def test_git_skill_examples_include_required_payload_fields() -> None:
    git_skill = ROOT / "boilerplate" / "skills" / "devtools" / "git.md"
    content = git_skill.read_text(encoding="utf-8")

    assert '"skill": "git"' in content
    assert '"confidence":' in content
    assert '"topic":' in content
    assert '"raw_text":' in content
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
poetry run pytest tests/test_boilerplate.py -v
```

Expected: FAIL because the current Git skill is not documented as an expert skill and examples omit `confidence`.

- [ ] **Step 3: Replace the Git skill Markdown**

Replace `boilerplate/skills/devtools/git.md` with:

```markdown
# Git Expert Skill

**Intent**: Use when the user asks a read-only question about Git commands, Git workflows, or Git concepts.

**Expert behavior:**
- Answer from local Git documentation only.
- Do not inspect the repository.
- Do not run repository-mutating commands.
- If local Git documentation is missing or insufficient, the handler must answer: "I could not find enough local documentation to answer safely."
- English answers are acceptable even when the user asks in another language.

**Field guidance:**
- `topic`: The Git command, workflow, or concept to explain. Strip filler words. Prefer the command name when clear (e.g. "rebase", "stash", "branch", "tag", "cherry-pick"). Use a short workflow phrase when no single command is clear (e.g. "squash commits", "undo commit safely").
- `context`: Any qualifier the user added (e.g. "last 3 commits", "remote branch", "without rewriting shared history") — omit if not stated.
- `raw_text`: Copy the user's original message verbatim.

**Examples:**
User: how to make a cherry-pick
Assistant: {"skill": "git", "confidence": 0.94, "topic": "cherry-pick", "raw_text": "how to make a cherry-pick"}

User: how can I delete a git tag from local
Assistant: {"skill": "git", "confidence": 0.93, "topic": "tag", "context": "delete local tag", "raw_text": "how can I delete a git tag from local"}

User: how do I squash the last 3 commits?
Assistant: {"skill": "git", "confidence": 0.95, "topic": "squash commits", "context": "last 3 commits", "raw_text": "how do I squash the last 3 commits?"}

User: what's the difference between reset and revert?
Assistant: {"skill": "git", "confidence": 0.9, "topic": "reset vs revert", "raw_text": "what's the difference between reset and revert?"}

User: stash changes and apply them later on another branch
Assistant: {"skill": "git", "confidence": 0.92, "topic": "stash", "context": "apply on another branch", "raw_text": "stash changes and apply them later on another branch"}
```

- [ ] **Step 4: Run boilerplate tests**

Run:

```bash
poetry run pytest tests/test_boilerplate.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boilerplate/skills/devtools/git.md tests/test_boilerplate.py
git commit -m "docs(git): 📝 define git expert skill"
```

---

### Task 6: Add Conversation Routing Coverage

**Files:**
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Write the failing conversation test**

Append this test to `tests/test_chat.py`:

```python
def test_engine_send_extracts_git_payload_when_topic_missing():
    state = RuntimeState(
        cwd="/tmp",
        skill_confidence_threshold=0.8,
        skills=[
            Skill(name="git", path="devtools/git.md", content="# Git Expert Skill")
        ],
    )
    engine = ConversationEngine(state)

    responses = [
        _make_ollama_response('{"skill": "git", "confidence": 0.95}'),
        _make_ollama_response(
            '{"skill": "git", "confidence": 0.95, "topic": "rebase", "raw_text": "How do I squash commits?"}'
        ),
    ]

    with (
        patch("mnemo8.chat.ollama.chat", side_effect=responses),
        patch("mnemo8.chat.run_skill", return_value="🌿 [Git - rebase]\nSummary: ok") as mock_run,
    ):
        response = asyncio.run(engine.send("How do I squash commits?"))

    mock_run.assert_called_once()
    assert response.resolved_skill is not None
    assert response.resolved_skill["skill"] == "git"
    assert response.resolved_skill["topic"] == "rebase"
    assert "🌿 [Git - rebase]" in response.display_text
```

- [ ] **Step 2: Run the test**

Run:

```bash
poetry run pytest tests/test_chat.py::test_engine_send_extracts_git_payload_when_topic_missing -v
```

Expected: PASS if the existing extraction recovery path already supports this. If it fails, inspect the failure before changing production code; the design expects no runtime changes.

- [ ] **Step 3: Commit if the test passes without production changes**

```bash
git add tests/test_chat.py
git commit -m "test(git): ✅ cover git payload extraction recovery"
```

If the test fails because the existing recovery path does not run for Git, make the smallest change in `mnemo8/chat.py` required to preserve the documented recovery behavior, then run the full `tests/test_chat.py` file and commit:

```bash
git add mnemo8/chat.py tests/test_chat.py
git commit -m "fix(chat): 🐛 recover incomplete git payloads"
```

---

### Task 7: Final Verification And Documentation Sync

**Files:**
- Modify: `docs/how-it-works.md`
- Modify: `boilerplate/CREATING_SKILLS.md`

- [ ] **Step 1: Add expert skill documentation**

In `docs/how-it-works.md`, add this short section after `## Skill/script contract`:

```markdown
## Expert skills

An expert skill is a normal leaf skill with a stricter script contract: it
answers from local evidence and abstains when evidence is insufficient. Expert
skills are not autonomous agents. They do not get a separate runtime, memory, or
tool loop.

The bundled Git skill is the first expert skill. It answers read-only Git
questions from local Git documentation and returns a safe abstention message
when local documentation is unavailable or insufficient.
```

In `boilerplate/CREATING_SKILLS.md`, add this section before `## Checklist for a New Skill`:

```markdown
## Expert Skills

Use an expert skill when a domain benefits from a handoff to a constrained
specialist, but does not need an autonomous agent.

Expert skills should:

- State the evidence source clearly.
- Keep payloads flat and easy for small local models.
- Avoid side effects unless the skill explicitly exists to perform an action.
- Return a clear abstention message when evidence is missing or insufficient.
- Prefer English prompts and examples for local model reliability.

The Git expert skill is the reference pattern: it answers from local Git
documentation only and does not inspect or modify repositories.
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
poetry run pytest tests/test_git_expert_script.py tests/test_boilerplate.py tests/test_chat.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run:

```bash
poetry run pytest
```

Expected: PASS, with Ollama integration tests skipped unless `DORI_RUN_OLLAMA_INTEGRATION=1` is set.

- [ ] **Step 4: Commit docs and any final fixes**

```bash
git add docs/how-it-works.md boilerplate/CREATING_SKILLS.md
git commit -m "docs(skills): 📝 document expert skill pattern"
```

- [ ] **Step 5: Manual smoke test with mocked expectations**

Run a direct script smoke test only if local Git docs and Ollama are available:

```bash
python boilerplate/scripts/git.py '{"skill": "git", "confidence": 0.95, "topic": "rebase", "raw_text": "How do I rebase?"}'
```

Expected: Either a `🌿 [Git - rebase]` answer grounded in local documentation, or the exact abstention message if local docs/model access are unavailable:

```text
🌿 [Git]: I could not find enough local documentation to answer safely.
```

Do not treat abstention as a failure in environments without local documentation or Ollama.
