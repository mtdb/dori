# How it works

Dori is a local-first terminal assistant. The public command is `dori`; the
internal engine lives in the `dori` package.

Dori separates model routing from deterministic execution:

- `DORI.md` defines persona and high-level behavior.
- `skills/` contains Markdown definitions for intents, fields, and examples.
- `scripts/` contains Python handlers that receive JSON from chat or run directly through `dori <skill-name>`.

Skills teach the model when to emit structured JSON. Scripts execute that JSON.

## Runtime

`dori init` creates `~/.dori`, copies the bundled boilerplate, and installs reminders and search presets selected during setup:

```text
~/.dori/
|-- DORI.md
|-- .manifest.json
|-- .history
|-- skills/
`-- scripts/
```

Reminder files are installed from `boilerplate/presets/reminders/`. The D-Bus preset uses `notify-send` for Linux desktop notifications. The template preset preserves the deterministic editable script for users who want to wire reminders to their own backend.

Web search files are installed from `boilerplate/presets/search/`. `ddgs` is
the default backend and works without an API key. `tavily` requires
`TAVILY_API_KEY` and uses Tavily's native answer generation. Both install as
the same top-level `web` skill and script, so runtime routing stays stable.

The source template is in `boilerplate/`, with default `DORI.md`, top-level
skills, grouped skills such as `devtools/`, and matching Python scripts. At
runtime, Dori always loads the active configuration from `~/.dori`, so users can
customize their local agent, skills, and scripts without editing the installed
package. The Textual TUI also stores the last 100 submitted messages in
`~/.dori/.history` and loads them on startup for ↑/↓ input recall.
`~/.dori/.manifest.json` stores md5 hashes for files managed by the bundled
boilerplate. `dori update` uses those hashes to overwrite only files that still
match their last installed content, while preserving locally edited files and
reporting each skipped path.

## Startup

The CLI entrypoint is registered in `pyproject.toml`:

```toml
[project.scripts]
dori = "dori.main:run"
```

`dori.main.run()` parses `dori`, `dori --prompt "..."`, `dori init`,
`dori update`, or `dori <skill-name>`. `dori init` calls `init_workspace()` and
copies missing boilerplate files into `~/.dori`. `dori update` calls
`update_workspace()` and refreshes only unmodified managed files according to
`.manifest.json`. Normal runs require `~/.dori`, load `DORI.md`, load the skill
tree, read VRAM information through `nvidia-smi` when available, build a
`RuntimeState`, and then run either one inline turn or the Textual TUI.

Direct skill commands use the installed script for that skill name and pass a
small CLI payload with `cli: true`. That keeps the core generic while still
letting action-oriented skills such as `commit` expose a native command.

The TUI handles display, input, history, clipboard, and VRAM refreshes. The
conversation logic lives in `dori.chat.ConversationEngine`, so TUI mode and
inline mode use the same behavior.

## System prompt

Each `ConversationEngine` starts with `build_system_prompt(state)`. The prompt
contains Dori's base identity, the current working directory, optional
`~/.dori/DORI.md` content, available top-level skills, and instructions for
emitting one JSON object when a skill clearly matches. Phrases such as "this
folder", "this directory", "current directory", and "here" refer to that
current working directory.

A skill payload looks like this:

```json
{"skill": "web", "confidence": 0.95, "raw_text": "Search for Python", "query": "Python"}
```

`confidence` must be between `0.0` and `1.0`. The default threshold is `0.8`;
override it with `DORI_SKILL_CONFIDENCE_THRESHOLD`.

## Skills

`load_skills()` recursively reads `~/.dori/skills`.

- Leaf skills are Markdown files except `_index.md`.
- Router skills are directories with child skills.

A leaf file such as `skills/web.md` becomes:

```python
Skill(name="web", path="web.md", content="<markdown content>")
```

Routers still work for grouped skills such as `devtools/`, but the bundled web
search capability is now a top-level leaf skill installed from the selected
preset.

## Turn lifecycle

For each user message, `ConversationEngine.send()` adds the message to history,
calls Ollama, stores the model response, parses a possible skill payload with
`parse_skill()`, and displays normal text if no valid payload exists. If the
payload targets a router, Dori resolves it to a leaf skill, extracts arguments,
validates and normalizes the payload with Pydantic, runs the matching script,
and returns `ChatResponse(raw_content, display_text, resolved_skill,
skill_output)`.

A successful web skill response is displayed as a grounded answer, for example:

```text
[ok] web
Python 3.14.0 was released on October 7, 2025.

Sources:
- https://www.python.org/...
- https://docs.python.org/...
```

## Payload parsing

`parse_skill()` accepts direct JSON or JSON fenced in Markdown:

```json
{"skill": "calendar", "confidence": 0.9, "raw_text": "Book lunch", "title": "Lunch", "when": "tomorrow"}
```

The payload must include `skill` and valid `confidence`. Legacy standalone JSON
without `confidence` is accepted as confidence `1.0`. When no skill runs,
`strip_skill_payload()` removes JSON blocks from the visible answer.

## Validation

Before execution, `validate_skill_payload()` validates the JSON with Pydantic.
Every payload requires `skill`, `confidence`, and `raw_text`.

Skill-specific fields: `reminders` needs `message` and `when`; `calendar`
needs `title` and `when`, with optional `duration` and `location`; `web` needs
`query` and accepts `freshness`; `git` needs `topic` and accepts `context`;
`docker` needs `question`.

Extra fields are allowed so users can extend scripts. If a required field is
missing, Dori asks for it and does not execute the script.

## Scripts

After validation, `run_skill(skill_name, skill_json, cwd=state.cwd)` looks for:

```text
~/.dori/scripts/<skill_name>.py
```

It runs:

```bash
python <script_path> '<payload-json>'
```

The script runs from Dori's launch directory, reads `sys.argv[1]`, parses JSON,
performs the action, and prints user-visible output to stdout. Non-zero exits
show stderr as an error. Missing scripts are reported as missing handlers.

For direct CLI execution, `dori <skill-name>` uses the same script path but
passes a payload with `cli: true` and `raw_text` set to the full command line.
That is useful for skills that are naturally command-shaped, such as `commit`.

## Skill/script contract

The link between a skill and a script is the leaf skill name:

```text
skills/web.md          -> scripts/web.py
skills/calendar.md     -> scripts/calendar.py
skills/devtools/git.md -> scripts/git.py
```

Markdown files may be nested, but scripts live flat in `scripts/`. A good skill
has a specific intent, clear field guidance, realistic JSON examples, a `skill`
field matching the filename, a same-named script, and deterministic stdout. The
skill guides the model; the script executes.

## Expert skills

An expert skill is a normal leaf skill with a stricter script contract: it
answers from local evidence and abstains when evidence is insufficient. Expert
skills are not autonomous agents. They do not get a separate runtime, memory, or
tool loop.

The bundled Git skill is the first expert skill. It answers read-only Git
questions from local Git documentation and returns a safe abstention message
when local documentation is unavailable or insufficient.

## Modes and variables

```bash
dori
dori --prompt "Summarize my open tasks"
dori init
DORI_DEBUG=1
DORI_SKILL_CONFIDENCE_THRESHOLD=0.7
TAVILY_API_KEY=tvly-...
DORI_WEB_MODEL=llama3.1:8b
```

`DORI_DEBUG` shows raw debugging content. The threshold variable controls the
minimum accepted skill confidence and is clamped to `0.0` to `1.0`.
`TAVILY_API_KEY` enables the Tavily preset. `DORI_WEB_MODEL` overrides the
local Ollama model used by the DDGS preset.

## Extending Dori

To add a leaf skill, create `~/.dori/skills/<name>.md`, define intent, field
guidance, and JSON examples, then create `~/.dori/scripts/<name>.py`. The script
should read `sys.argv[1]`, parse JSON, execute deterministically, and print a
clear result. If you want the skill to be runnable as `dori <name>`, have the
script accept the CLI payload form as well. Test the script directly, then test
through `dori --prompt` and, if applicable, `dori <name>`.

To add a category, create `~/.dori/skills/<category>/_index.md`, add child
skills in that directory, and create one flat script per child skill in
`~/.dori/scripts/`.
