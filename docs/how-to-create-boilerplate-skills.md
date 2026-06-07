# Creating New Skills for Dori

This guide covers how to add a skill to the boilerplate — from the skill definition file to the Python handler script.

---

## How Skills Work

When a user sends a message, the LLM reads the skill files to decide if the intent matches. If it does, it outputs a **JSON payload** instead of a text response. The runtime then dispatches that payload to the corresponding Python script, which executes the action deterministically.

Some skills can also be executed directly as `dori <skill-name>`. In that case,
the runtime still calls the same script, but it passes a CLI-oriented payload
with `cli: true`. That keeps the core generic and lets only command-shaped
skills expose a direct command.

```
User message
    → LLM reads skills/ and matches intent
    → LLM outputs JSON: {"skill": "my-skill", "confidence": 0.92, "raw_text": "...", ...}
    → Runtime calls scripts/my-skill.py with the JSON as a CLI argument
    → Script executes and prints output
```

Every skill payload must include:

- `skill`: The leaf skill name, matching `scripts/<skill>.py`.
- `confidence`: A number from `0.0` to `1.0`. Dori only runs the skill when this meets the configured confidence threshold.
- `raw_text`: The user's original message copied verbatim.

---

## Directory Layout

```
boilerplate/
├── DORI.md                 # Persona and routing instructions for the LLM
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
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: <example user message>
Assistant: {"skill": "my-skill", "confidence": 0.92, "field_name": "extracted value", "raw_text": "<same message>"}

User: <edge case or variation>
Assistant: {"skill": "my-skill", "confidence": 0.86, "field_name": "extracted value", "raw_text": "<same message>"}
```

### Rules

- **Intent line** — one sentence that starts with "Use when the user wants to…". This is what the LLM uses to decide whether to activate the skill. Be specific.
- **Field guidance** — describe every field the JSON can contain. State clearly when optional fields should be omitted (not set to `null`).
- **`confidence`** — always include this field in every example. Use realistic values: high confidence for direct matches, lower but still above threshold for looser matches.
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
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Save a note: buy oat milk
Assistant: {"skill": "notes", "confidence": 0.95, "content": "buy oat milk", "raw_text": "Save a note: buy oat milk"}

User: Jot down 'call dentist' under health
Assistant: {"skill": "notes", "confidence": 0.92, "content": "call dentist", "tag": "health", "raw_text": "Jot down 'call dentist' under health"}
```

---

## Step 2 — Write the Handler Script (`scripts/my-skill.py`)

Handler scripts receive the JSON payload as a CLI argument, extract fields, and execute the action.
If the skill is also meant to be callable as `dori <skill-name>`, the script
should accept the CLI payload form too.

### Structure

```python
import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
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
        print("Error: Invalid JSON payload provided to notes script.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Rules

- **Always validate** that `sys.argv[1]` exists before parsing.
- **Use `.get()` with defaults** for required fields so the script never crashes silently.
- **Use `.get()` without a default** (returns `None`) for optional fields, then check before using them.
- **Print deterministic output** — one clear result the user can read. Prefer one line; use multiple lines when the answer naturally needs steps or command output.
- **Exit with `sys.exit(1)`** on error, print a clear error message to stderr.
- **Never leave side effects partially applied** — if the real implementation writes to a file or calls an API, do it atomically or roll back on failure.
- **If the skill is command-shaped**, accept the `{"cli": true, ...}` payload and decide whether to run the full interactive workflow or a lightweight command response.
- **If the skill needs follow-up input**, use the stable public API in `dori.script`:
  `ask(prompt, default=None)`, `confirm(prompt, default=False)`, and
  `choose(prompt, choices, default=None)`. These work in chat and in direct
  `dori <skill>` execution. Do not read directly from stdin for follow-up
  prompts.
- **Treat `dori --prompt` as single-turn only**. Interactive scripts should
  fail with a clear message telling the user to use the TUI chat or run the
  skill directly.

---

## Step 3 — Register the Skill in `DORI.md` (if needed)

`DORI.md` is the system prompt. If your skill changes routing behavior or introduces a new category, add a brief note there. For simple leaf skills that don't affect routing, no change is needed.

---

## Nested / Grouped Skills

When several related skills share a common trigger (e.g. different types of search), group them under a subdirectory with an `_index.md` router.

### `skills/media/_index.md` — Router

```markdown
# Media Router

**Intent**: Use when the user wants help with media-related tasks.

**Experts available**: images, videos
```

The router lists the sub-skill names. The LLM picks the best match and loads the corresponding sub-skill file from the same directory.

### Sub-skill files

Each sub-skill (e.g. `skills/media/images.md`) follows the same structure as a top-level skill file. The `"skill"` key in the JSON payload should match the sub-skill name (`"images"`, `"videos"`, etc.), and the corresponding script lives at `scripts/images.py`, `scripts/videos.py`, etc.

The bundled web search capability is intentionally not modeled as a grouped
router. Dori installs one top-level `web` skill from `boilerplate/presets/search/`
so different providers can share the same runtime name and payload contract.

---

## Expert Skills

Use an expert skill when a domain benefits from a handoff to a constrained
specialist, but does not need an autonomous agent. If the same capability should
also be callable as `dori <skill-name>`, keep that behavior in the same script
instead of adding special core logic.

Expert skills should:

- State the evidence source clearly in the skill file and handler prompt.
- Keep payloads flat and easy for small local models.
- State whether the handler is read-only or action-taking.
- Avoid side effects unless the skill explicitly exists to perform an action.
- Return a clear abstention message when evidence is missing or insufficient.
- Prefer English prompts and examples for local model reliability.
- Treat user input and optional context as untrusted.
- Validate generated expert output before printing it.

The Git expert skill is the reference pattern: it answers from local Git
documentation only and does not inspect or modify repositories.

### Expert skill file pattern

```markdown
# <Domain> Expert Skill

**Intent**: Use when the user asks an informational question about <domain>.

**Expert behavior:**
- The handler is read-only.
- Answer from <specific evidence source> only.
- Do not inspect unrelated local state.
- Do not run mutating commands.
- If evidence is missing or insufficient, answer: "<stable abstention message>"
- Write answers in English for local model reliability.

**Field guidance:**
- `topic`: The command, workflow, or concept to explain. Strip filler words.
- `context`: Any qualifier the user added — omit if not stated.
- `confidence`: Numeric confidence from 0.0 to 1.0.
- `raw_text`: Copy the user's original message verbatim.

**Examples:**
User: <domain question>
Assistant: {"skill": "<name>", "confidence": 0.93, "topic": "<normalized topic>", "raw_text": "<domain question>"}
```

### Expert handler pattern

Expert handlers should split the work into small, testable functions:

- Normalize the user topic to a supported evidence lookup.
- Retrieve local or deterministic evidence.
- Build a constrained prompt that labels user input as untrusted.
- Ask the model for an answer only from that evidence.
- Validate the answer format before printing.
- Return the stable abstention message for unknown topics, missing evidence, model errors, or unsafe output.

For example, the Git expert script normalizes phrases such as "squash commits"
to `rebase`, reads local Git help/manpage text, asks a read-only Git expert
prompt to answer from that text, and abstains if the output does not match the
expected format.

---

## Checklist for a New Skill

- [ ] **Skill file** created at `skills/<name>.md` (or `skills/<group>/<name>.md` for nested)
- [ ] Intent line starts with "Use when the user wants to…" and is specific
- [ ] All JSON fields documented in **Field guidance**, with omit conditions for optional ones
- [ ] `confidence` included in field guidance and in every example
- [ ] `raw_text` included in field guidance and in every example
- [ ] 2–3 examples covering common case and at least one variation
- [ ] **Script** created at `scripts/<name>.py`
- [ ] Script validates `sys.argv[1]` before parsing
- [ ] Required fields use `.get("field", "default")`; optional fields use `.get("field")`
- [ ] Output is deterministic and readable
- [ ] Error path prints a message to stderr and exits with code 1
- [ ] If grouped: `_index.md` router lists the new skill name
- [ ] Manual test: run `python scripts/<name>.py '{"skill":"<name>","confidence":0.9,"raw_text":"test"}'`
- [ ] If command-shaped, manual test `dori <name>` from a repo with the skill installed

For expert skills, also check:

- [ ] Skill file states the evidence source and side-effect policy
- [ ] Stable abstention message is documented and implemented
- [ ] Handler treats user-provided text as untrusted context
- [ ] Handler validates generated output before printing
- [ ] Tests cover unknown topic, missing evidence, model failure, and invalid output

---

## Testing a Skill Manually

You can test the handler directly before wiring it into the runtime:

```bash
# Test with a full payload
python boilerplate/scripts/my-skill.py '{"skill": "my-skill", "confidence": 0.95, "content": "buy milk", "raw_text": "save a note to buy milk"}'

# Test with missing optional field
python boilerplate/scripts/my-skill.py '{"skill": "my-skill", "confidence": 0.95, "content": "buy milk", "raw_text": "save a note to buy milk"}'

# Test error handling (missing payload)
python boilerplate/scripts/my-skill.py
```

Expected: the successful runs print deterministic output; the last run prints
an error to stderr and exits 1.

---

## Tips for Small / Local Models

- **Be explicit in field guidance** — small models struggle with ambiguous instructions. State exactly what to include and what to strip.
- **Use 2–3 short, varied examples** — more examples help small models generalize; fewer avoids context bloat.
- **Keep JSON payloads flat** — avoid nested objects. Small models are more reliable with flat key-value structures.
- **Name skills with short, common words** — the skill name becomes a JSON key and must be unambiguous (`"calendar"` beats `"event-scheduler"`).
- **One skill, one action** — avoid multi-purpose skills. If a skill routes to different handlers based on a field, split it into separate skills or use the nested pattern.
