# Design: Port legacy routing pipeline to mnemo8 CLI

**Date:** 2026-04-28  
**Approach:** B — Prompt hardening + session state + entity repair

## Context

The current mnemo8 CLI loads `skills/*.md` and `scripts/*.py` from the working directory, injects all skill content into a single system prompt, and dispatches a subprocess call to `scripts/<name>.py` when the LLM returns JSON with a `"skill"` key. It has no slot memory, no entity repair, and no missing-field handling.

The legacy `mnemo8-django` implementation has a proven routing pipeline: structured JSON extraction, per-intent entity repair (regex + dateparser), cross-turn slot memory, and a clarification flow for missing fields. This design ports the essential parts of that pipeline into the lightweight CLI, keeping `skills/*.md` + `scripts/*.py` as-is.

## Scope

- One new file: `mnemo8/repair.py` (~60 lines)
- Two modified files: `mnemo8/chat.py`, `mnemo8/models.py`
- One dependency added: `dateparser>=1.1.0`
- `scripts/reminders.py` and `skills/reminders.md` remain unchanged

## Data Flow

```
User input
  → LLM (single call, improved structured prompt)
  → JSON parse (existing regex extraction)
  → merge into resolved_entities[skill_name]
  → entity repair (skill-specific)
  → missing field check
      → missing: ask clarification, store pending_intent
      → complete: dispatch scripts/<name>.py with merged JSON
```

On each subsequent turn, the conversation history carries prior context so the LLM can fill in missing slots naturally. Merged partial state persists in `RuntimeState` (in-memory, session-scoped).

## Section 1: Session State

`RuntimeState` gains two fields:

```python
resolved_entities: dict[str, dict]   # {skill_name: {field: value}}
pending_intent: str | None            # skill name awaiting slot completion
```

After a successful JSON parse, new fields are merged into `resolved_entities[skill_name]` (new values win). If `pending_intent` is set and the LLM returns a different skill or plain text, the pending intent is silently abandoned.

## Section 2: Prompt Structure

`build_system_prompt()` wraps each skill with an explicit schema block instead of dumping raw content:

```
--- Skill: reminders ---
When the user's intent matches this skill, output ONLY valid JSON:
{"skill": "reminders", "message": "<task, no time phrases>", "when": "<time expression>", "raw_text": "<original user message>"}
Required fields: skill, message, when
Optional fields: raw_text

<skill.content>
---
```

`raw_text` is a new field the LLM is asked to echo — it lets the repair layer re-parse the original message if the extracted `when` is ambiguous.

## Section 3: Entity Repair

New file `mnemo8/repair.py` exposes a single function:

```python
def repair(skill_name: str, entities: dict) -> dict
```

Dispatches to a skill-specific repair function. For `reminders`:

1. **Strip filler from `message`** — compiled regex removes "remind me to", "recuérdame", "please", "set a reminder to", etc.
2. **Extract and normalize `when`** — `dateparser.search_dates()` on `raw_text` (falling back to `entities["when"]`) returns a list of `(phrase, datetime)` pairs; pick the first result. Converts to ISO 8601. Raises `ValueError` if unparseable or in the past.
3. **Remove time phrase from `message`** — strips the matched time substring from the cleaned message text.

For skills with no registered repair function, `repair()` returns `entities` unchanged.

## Section 4: Missing Field Check and Clarification

Required fields are declared in `chat.py` as a plain dict:

```python
REQUIRED_FIELDS = {
    "reminders": ["message", "when"],
}
```

After repair, if any required fields are absent from the merged entity dict:
- Set `state.pending_intent = skill_name`
- Reply with a hardcoded clarification string per skill (e.g. for `reminders` with missing `when`: `"Got it. What time should I set the reminder for?"`). Not LLM-generated.
- On the next turn, merge the new JSON into the stored partial state, run repair again, and re-check

Once all required fields are present, dispatch to `scripts/<skill_name>.py` with the fully merged JSON and clear `pending_intent`.

## Dependencies

Add to `pyproject.toml`:

```
dateparser>=1.1.0
```

## What is not changing

- `skills/*.md` files — no frontmatter parsing, no schema changes
- `scripts/*.py` files — receive cleaner JSON but same calling convention
- Ollama model and single-call approach
- Subprocess dispatch mechanism
