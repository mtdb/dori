# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Mnemo8 is a local-first, folder-native agent runtime CLI. It discovers `AGENTS.md` (system persona/instructions) and `skills/` (declarative skill definitions) from the **current working directory at runtime** — not from the repo root — so the runtime context is entirely folder-bound. Ollama (`llama3.1:8b`) is the default LLM backend.

## Commands

```bash
# Install in editable mode (required before running)
pip install -e .

# Run the CLI from any directory
mnemo8

# Initialize a workspace with default AGENTS.md and skills/reminders.md
mnemo8 init
```

There are no tests or linter configs yet.

## Architecture

The runtime lifecycle in `mnemo8/main.py`:
1. Load `AGENTS.md` from CWD → `loader.load_agents()`
2. Load `skills/*.md` from CWD → `loader.load_skills()`
3. Build `RuntimeState` (dataclass in `models.py`)
4. Start REPL loop → `chat.start_chat()`

**Skill dispatch flow** (`chat.py`): The LLM is prompted to emit a raw JSON block when a user intent matches a skill. `chat.py` parses the response for `{"skill": "<name>", ...}`, then runs `scripts/<name>.py` as a subprocess with the JSON payload as `argv[1]`. If no JSON skill match is found, the LLM response is rendered as Markdown.

**Key design constraint**: skills are markdown files (`skills/*.md`) that are injected verbatim into the system prompt. The execution is handled by paired Python scripts in `scripts/`. New skills require both a `.md` declaration and a `scripts/<name>.py` handler.

`commands.py` contains the `init_workspace()` function and default templates for `AGENTS.md` and `skills/reminders.md` — this is where the default persona (Noctis) is defined.

## Runtime File Conventions

When `mnemo8` is run from a project directory (not this repo), it expects:
- `AGENTS.md` — system prompt / persona definition
- `skills/*.md` — each file declares intent triggers, input/output JSON schema, and examples
- `scripts/<skill_name>.py` — receives parsed JSON via `argv[1]`, prints output to stdout
- `.mnemo8/` — reserved for runtime state, cache, embeddings (not yet implemented)

## Dependencies

- `rich` — terminal UI (console, prompts, markdown rendering)
- `ollama` — local LLM calls (must have Ollama running locally with `llama3.1:8b` pulled)
- No database, no cloud services by default
