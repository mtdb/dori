# Creating New Skills for Dori

This guide covers how to add a skill to the boilerplate — from the skill definition file to the Python handler script.

---

## How Skills Work

When a user sends a message, the LLM reads the skill files to decide if the intent matches. If it does, it outputs a **JSON payload** instead of a text response. The runtime then dispatches that payload to the corresponding Python script, which executes the action deterministically.

```
User message
    → LLM reads skills/ and matches intent
    → LLM outputs JSON: {"skill": "my-skill", "field": "value", ...}
    → Runtime calls scripts/my-skill.py with the JSON as a CLI argument
    → Script executes and prints output
```

---

## Directory Layout

```
boilerplate/
├── AGENTS.md               # Persona and routing instructions for the LLM
├── skills/
│   ├── my-skill.md         # Skill definition (intent, fields, examples)
│   └── search/
│       ├── _index.md       # Router for grouped/nested skills
│       └── my-sub-skill.md # Sub-skill definition
└── scripts/
    └── my-skill.py         # Handler that receives and executes the JSON payload
```

---

## Step 1 — Write the Skill File (`skills/my-skill.md`)

Skill files are the LLM's guide for recognizing user intent and constructing the JSON payload.

### Structure

```markdown
# <Skill Name> Skill

**Intent**: Use when the user wants to <description of triggering situation>.

**Field guidance:**
- `field_name`: <what goes here — be specific about format and when to omit>
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: <example user message>
Assistant: {"skill": "my-skill", "field_name": "extracted value", "raw_text": "<same message>"}

User: <edge case or variation>
Assistant: {"skill": "my-skill", "field_name": "extracted value", "raw_text": "<same message>"}
```

### Rules

- **Intent line** — one sentence that starts with "Use when the user wants to…". This is what the LLM uses to decide whether to activate the skill. Be specific.
- **Field guidance** — describe every field the JSON can contain. State clearly when optional fields should be omitted (not set to `null`).
- **`raw_text`** — always include this field in every skill. It carries the verbatim user message for logging, debugging, and future reference.
- **Examples** — provide 2–3 examples covering the common case and at least one variation (with optional fields, with omitted fields, different phrasing).
- Keep examples realistic. The LLM will pattern-match against them.

### Minimal skill file example

```markdown
# Notes Skill

**Intent**: Use when the user wants to save a note, jot something down, or write a memo.

**Field guidance:**
- `content`: The note body — strip filler words (e.g. "buy oat milk", not "save a note to buy oat milk")
- `tag`: A category label if mentioned (e.g. "shopping", "work") — omit if not stated
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Save a note: buy oat milk
Assistant: {"skill": "notes", "content": "buy oat milk", "raw_text": "Save a note: buy oat milk"}

User: Jot down 'call dentist' under health
Assistant: {"skill": "notes", "content": "call dentist", "tag": "health", "raw_text": "Jot down 'call dentist' under health"}
```

---

## Step 2 — Write the Handler Script (`scripts/my-skill.py`)

Handler scripts receive the JSON payload as a CLI argument, extract fields, and execute the action.

### Structure

```python
import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload")
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])

        # Extract fields — use .get() with a sensible default
        content = payload.get("content", "unknown")
        tag = payload.get("tag")           # Optional field — may be None

        # Build output
        line = f"📝 [Notes]: Saved '{content}'"
        if tag:
            line += f" (tag: {tag})"
        line += "."
        print(line)

    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to notes script.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Rules

- **Always validate** that `sys.argv[1]` exists before parsing.
- **Use `.get()` with defaults** for required fields so the script never crashes silently.
- **Use `.get()` without a default** (returns `None`) for optional fields, then check before using them.
- **Print deterministic output** — one clear line the user can read. Use an emoji prefix matching the skill's domain for quick scanning.
- **Exit with `sys.exit(1)`** on error, print a clear error message to stdout.
- **Never leave side effects partially applied** — if the real implementation writes to a file or calls an API, do it atomically or roll back on failure.

---

## Step 3 — Register the Skill in `AGENTS.md` (if needed)

`AGENTS.md` is the system prompt. If your skill changes routing behavior or introduces a new category, add a brief note there. For simple leaf skills that don't affect routing, no change is needed.

---

## Nested / Grouped Skills

When several related skills share a common trigger (e.g. different types of search), group them under a subdirectory with an `_index.md` router.

### `skills/search/_index.md` — Router

```markdown
# Search Router

**Intent**: Use when the user wants to search, look something up, or find information online.

**Experts available**: web, images, news, maps, code
```

The router lists the sub-skill names. The LLM picks the best match and loads the corresponding sub-skill file from the same directory.

### Sub-skill files

Each sub-skill (e.g. `skills/search/news.md`) follows the same structure as a top-level skill file. The `"skill"` key in the JSON payload should match the sub-skill name (`"news"`, `"maps"`, etc.), and the corresponding script lives at `scripts/news.py`, `scripts/maps.py`, etc.

---

## Checklist for a New Skill

- [ ] **Skill file** created at `skills/<name>.md` (or `skills/<group>/<name>.md` for nested)
- [ ] Intent line starts with "Use when the user wants to…" and is specific
- [ ] All JSON fields documented in **Field guidance**, with omit conditions for optional ones
- [ ] `raw_text` included in field guidance and in every example
- [ ] 2–3 examples covering common case and at least one variation
- [ ] **Script** created at `scripts/<name>.py`
- [ ] Script validates `sys.argv[1]` before parsing
- [ ] Required fields use `.get("field", "default")`; optional fields use `.get("field")`
- [ ] Output is a single, readable line with an emoji prefix
- [ ] Error path prints a message and exits with code 1
- [ ] If grouped: `_index.md` router lists the new skill name
- [ ] Manual test: run `python scripts/<name>.py '{"skill":"<name>","raw_text":"test"}'`

---

## Testing a Skill Manually

You can test the handler directly before wiring it into the runtime:

```bash
# Test with a full payload
python boilerplate/scripts/my-skill.py '{"skill": "my-skill", "content": "buy milk", "raw_text": "save a note to buy milk"}'

# Test with missing optional field
python boilerplate/scripts/my-skill.py '{"skill": "my-skill", "content": "buy milk", "raw_text": "save a note to buy milk"}'

# Test error handling (missing payload)
python boilerplate/scripts/my-skill.py
```

Expected: each run prints one clean line; the last run prints an error and exits 1.

---

## Tips for Small / Local Models

- **Be explicit in field guidance** — small models struggle with ambiguous instructions. State exactly what to include and what to strip.
- **Use 2–3 short, varied examples** — more examples help small models generalize; fewer avoids context bloat.
- **Keep JSON payloads flat** — avoid nested objects. Small models are more reliable with flat key-value structures.
- **Name skills with short, common words** — the skill name becomes a JSON key and must be unambiguous (`"calendar"` beats `"event-scheduler"`).
- **One skill, one action** — avoid multi-purpose skills. If a skill routes to different handlers based on a field, split it into separate skills or use the nested pattern.
