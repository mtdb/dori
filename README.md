# Dori

Dori is a local-first terminal assistant designed to work well with small local models.

It is not trying to be "Claude Code, but local." The goal is narrower and more honest: help you from the terminal by routing clear requests into deterministic scripts, with behavior you can inspect, edit, and extend yourself.

## What Dori Is

- A terminal assistant that runs locally
- A tool router that turns clear intents into structured JSON
- A script-backed system you can customize in `~/.dori`
- A better fit for 8B-class local models than open-ended autonomous agents

## What Dori Is Not

- Not a full autonomous coding agent
- Not a replacement for larger hosted models on complex repo-wide tasks
- Not a hidden tool loop that edits files and runs commands without a clear contract
- Not magic: reliability matters more than agent theater

If you expect broad autonomous code editing, long tool loops, or strong performance on hard software tasks with a small local model, Dori will probably feel intentionally constrained.

## Why This Project Exists

Most local assistants either:

- imitate larger coding agents and become unreliable on small models, or
- stay so simple that they are hard to extend into something genuinely useful.

Dori aims for the middle:

- local-first
- fast to start
- understandable
- extendable with plain Markdown and Python
- optimized for reliability over autonomy

The model decides when a request matches a skill and fills structured arguments. A deterministic script does the real work.

## Good Fit

Dori is a good fit if you want:

- a personal terminal assistant powered by Ollama
- a system you can inspect and customize end to end
- practical local workflows such as web lookup, reminders, calendar actions, git help, docker help, or folder analysis
- predictable behavior from small local models

Dori is a poor fit if you want:

- a general-purpose coding agent with deep autonomy
- multi-step repo mutation driven mostly by the model
- the same capability level as Claude Code, Codex, or similar systems

## How It Works

1. Dori loads its persona from `~/.dori/DORI.md`.
2. It discovers installed skills from `~/.dori/skills/`.
3. The local model either answers normally or emits one JSON payload for a matching skill.
4. Dori validates that payload and runs the matching script from `~/.dori/scripts/`.
5. The script prints the result back to the user.

This separation is the core idea:

- skills teach the model when to act
- scripts perform the action deterministically

## Current Product Shape

Today Dori includes:

- a Textual TUI
- one-off prompt mode with `dori --prompt`
- direct skill execution with `dori <skill-name>`
- local persona and skill loading from `~/.dori`
- bundled starter skills for tasks like reminders, calendar, web, git, docker, commit, and folder analysis
- update-safe boilerplate management through `dori init` and `dori update`

## Requirements

- Python 3.11+
- Ollama running locally
- a local model available in Ollama

By default, Dori uses `llama3.1:8b`.

## Quickstart

1. Install:

```bash
pip install dori
```

2. Initialize runtime files:

```bash
dori init
```

3. Start the assistant:

```bash
dori
```

4. Or send a single prompt:

```bash
dori --prompt "Summarize my open tasks"
```

## Global Install

For a global CLI install, prefer `pipx`:

```bash
pipx install dori
```

To track local development changes:

```bash
pipx install -e .
```

Alternative with user-local `pip`:

```bash
python3 -m pip install --user dori
```

For local development from a cloned repository:

```bash
pip install -e .
```

## Runtime Layout

Dori stores its runtime state in `~/.dori`:

```text
~/.dori/
|-- DORI.md
|-- .manifest.json
|-- .history
|-- skills/
`-- scripts/
```

`dori init` copies the bundled boilerplate into that directory and asks you to choose:

- a reminders backend
- a search backend

During setup the prompt text is `Choose search backend`, with `ddgs` as the
default and `tavily` available when you want Tavily-backed answers.

`dori update` refreshes managed files that still match their last installed hash and preserves files you have edited locally.

The TUI stores the last 100 submitted messages in `.history` so you can recall them with `↑` and `↓` in new sessions.

## Search Backends

Search defaults to DDGS for zero-key web answers.

For Tavily-backed search, export:

```bash
export TAVILY_API_KEY="tvly-..."
```

For DDGS-backed search, Dori uses a local Ollama model to synthesize an English answer from retrieved evidence. Override that model with:

```bash
export DORI_WEB_MODEL="llama3.1:8b"
```

Both search backends return a direct answer followed by `Sources:` and two or three URLs.

## Better Prompts With Ctrl+T

Small local models often respond better to English prompts. The TUI includes a built-in translation shortcut:

- press `Ctrl+T` while writing a message
- Dori translates your draft into natural English before sending it

It tries to preserve code, commands, flags, file paths, URLs, identifiers, and quoted literals.

## Extending Dori

The main customization story is intentionally simple:

1. add a skill Markdown file under `~/.dori/skills/`
2. add a same-named Python script under `~/.dori/scripts/`
3. make the script read the JSON payload and print a clear result

This makes Dori easier to inspect and evolve than systems that hide everything behind a large prompt or a complex agent runtime.

## Development Notes

- Public packaging and CLI surface are `dori`
- Internal modules live under the `dori` package
- Boilerplate and onboarding text should refer to Dori

## Tests

Run the default test suite:

```bash
poetry run pytest
```

Integration tests that call Ollama are skipped by default. To run them, make sure Ollama is running and `llama3.1:8b` is installed:

```bash
ollama pull llama3.1:8b
DORI_RUN_OLLAMA_INTEGRATION=1 poetry run pytest tests/test_ollama_integration.py
```

The Ollama integration tests use `llama3.1:8b` with `seed: 42` and `temperature: 0` for predictable routing checks.
