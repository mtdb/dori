# How it works

Dori is a local-first terminal assistant. The public command is `dori`; the
internal engine lives in the `mnemo8` package.

Dori separates model routing from deterministic execution:

- `AGENTS.md` defines persona and high-level behavior.
- `skills/` contains Markdown definitions for intents, fields, and examples.
- `scripts/` contains Python handlers that receive JSON and execute actions.

Skills teach the model when to emit structured JSON. Scripts execute that JSON.

## Runtime

`dori init` creates `~/.dori` and copies the bundled boilerplate:

```text
~/.dori/
|-- AGENTS.md
|-- skills/
`-- scripts/
```

The source template is in `boilerplate/`, with default `AGENTS.md`, grouped
skills such as `search/` and `devtools/`, and matching Python scripts. At
runtime, Dori always loads the active configuration from `~/.dori`, so users can
customize their local agent, skills, and scripts without editing the installed
package.

## Startup

The CLI entrypoint is registered in `pyproject.toml`:

```toml
[project.scripts]
dori = "mnemo8.main:run"
```

`mnemo8.main.run()` parses `dori`, `dori --prompt "..."`, or `dori init`.
`dori init` calls `init_workspace()` and copies missing boilerplate files into
`~/.dori`. Normal runs require `~/.dori`, load `AGENTS.md`, load the skill tree,
read VRAM information through `nvidia-smi` when available, build a
`RuntimeState`, and then run either one inline turn or the Textual TUI.

The TUI handles display, input, history, clipboard, and VRAM refreshes. The
conversation logic lives in `mnemo8.chat.ConversationEngine`, so TUI mode and
inline mode use the same behavior.

## System prompt

Each `ConversationEngine` starts with `build_system_prompt(state)`. The prompt
contains Dori's base identity, optional `~/.dori/AGENTS.md` content, available
top-level skills, and instructions for emitting one JSON object when a skill
clearly matches.

A skill payload looks like this:

```json
{"skill": "web", "confidence": 0.95, "raw_text": "Search for Python", "query": "Python"}
```

`confidence` must be between `0.0` and `1.0`. The default threshold is `0.8`;
override it with `MNEMO8_SKILL_CONFIDENCE_THRESHOLD`.

## Skills

`load_skills()` recursively reads `~/.dori/skills`.

- Leaf skills are Markdown files except `_index.md`.
- Router skills are directories with child skills.

A leaf file such as `skills/search/web.md` becomes:

```python
Skill(name="web", path="search/web.md", content="<markdown content>")
```

A router uses its `_index.md` content when present, or a generated fallback
description. For example, `skills/search/_index.md` creates a `search` router,
while `web.md`, `images.md`, and `news.md` become leaf skills.

## Turn lifecycle

For each user message, `ConversationEngine.send()` adds the message to history,
calls Ollama, stores the model response, parses a possible skill payload with
`parse_skill()`, and displays normal text if no valid payload exists. If the
payload targets a router, Dori resolves it to a leaf skill, extracts arguments,
validates and normalizes the payload with Pydantic, runs the matching script,
and returns `ChatResponse(raw_content, display_text, resolved_skill,
skill_output)`.

A successful skill response is displayed as:

```text
[ok] web
[Web Search]: Searching the web for 'Python'...
```

Low-confidence JSON, invalid JSON, and invalid payloads do not run scripts.
Dori answers normally or asks for the missing field.

## Payload parsing

`parse_skill()` accepts direct JSON or JSON fenced in Markdown:

```json
{"skill": "calendar", "confidence": 0.9, "raw_text": "Book lunch", "title": "Lunch", "when": "tomorrow"}
```

The payload must include `skill` and valid `confidence`. Legacy standalone JSON
without `confidence` is accepted as confidence `1.0`. When no skill runs,
`strip_skill_payload()` removes JSON blocks from the visible answer.

## Routers

Routers organize related skills. For example, `search` can route to `web`,
`images`, `news`, `maps`, or `code`.

If the model selects:

```json
{"skill": "search", "confidence": 0.91, "raw_text": "look up Madrid weather"}
```

Dori does not run `scripts/search.py`. It asks the model to choose one child,
extracts the final payload for that leaf skill, validates it, and runs
`scripts/<leaf>.py`.

## Validation

Before execution, `validate_skill_payload()` validates the JSON with Pydantic.
Every payload requires `skill`, `confidence`, and `raw_text`.

Skill-specific fields: `reminders` needs `message` and `when`; `calendar`
needs `title` and `when`, with optional `duration` and `location`; `web`,
`images`, `news`, and `code` need `query`; `news` also accepts `since`; `maps`
needs `place` and accepts `directions_from`; `git` needs `topic` and accepts
`context`; `docker` needs `question`.

Extra fields are allowed so users can extend scripts. If a required field is
missing, Dori asks for it and does not execute the script.

## Scripts

After validation, `run_skill(skill_name, skill_json)` looks for:

```text
~/.dori/scripts/<skill_name>.py
```

It runs:

```bash
python <script_path> '<payload-json>'
```

The script reads `sys.argv[1]`, parses JSON, performs the action, and prints
user-visible output to stdout. Non-zero exits show stderr as an error. Missing
scripts are reported as missing handlers.

## Skill/script contract

The link between a skill and a script is the leaf skill name:

```text
skills/search/web.md   -> scripts/web.py
skills/calendar.md     -> scripts/calendar.py
skills/devtools/git.md -> scripts/git.py
```

Markdown files may be nested, but scripts live flat in `scripts/`. A good skill
has a specific intent, clear field guidance, realistic JSON examples, a `skill`
field matching the filename, a same-named script, and deterministic stdout. The
skill guides the model; the script executes.

## Modes and variables

```bash
dori
dori --prompt "Summarize my open tasks"
dori init
MNEMO8_DEBUG=1
MNEMO8_SKILL_CONFIDENCE_THRESHOLD=0.7
```

`MNEMO8_DEBUG` shows raw debugging content. The threshold variable controls the
minimum accepted skill confidence and is clamped to `0.0` to `1.0`.

## Extending Dori

To add a leaf skill, create `~/.dori/skills/<name>.md`, define intent, field
guidance, and JSON examples, then create `~/.dori/scripts/<name>.py`. The script
should read `sys.argv[1]`, parse JSON, execute deterministically, and print a
clear result. Test the script directly, then test through `dori --prompt`.

To add a category, create `~/.dori/skills/<category>/_index.md`, add child
skills in that directory, and create one flat script per child skill in
`~/.dori/scripts/`.
