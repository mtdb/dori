# Dori

Dori is the public product: a local-first terminal assistant that loads its persona from `AGENTS.md`, discovers declarative `skills/`, and routes requests into deterministic scripts.

## Interface

- Distribution: `dori`
- CLI command: `dori`
- Runtime home: `~/.dori`

## Quickstart

1. Install in editable mode:

```bash
pip install -e .
```

2. Initialize Dori's runtime files:

```bash
dori init
```

3. Start the assistant:

```bash
dori
```

4. Or send a one-off prompt:

```bash
dori --prompt "Summarize my open tasks"
```

## Global install

For a global CLI install, prefer `pipx`:

```bash
pipx install .
```

If you want the installed command to track local development changes:

```bash
pipx install -e .
```

Alternative with user-local `pip`:

```bash
python3 -m pip install --user .
```

## Runtime layout

Dori stores its runtime state in `~/.dori`:

```text
~/.dori/
├── AGENTS.md
├── skills/
└── scripts/
```

`dori init` copies the boilerplate `AGENTS.md`, `skills/`, and `scripts/` into that directory.

## How it works

1. Dori builds a system prompt from `~/.dori/AGENTS.md` and available skills.
2. The `mnemo8` engine asks the local model to either answer normally or emit a skill JSON payload.
3. If a skill is selected, Dori runs the matching script from `~/.dori/scripts/`.
4. The TUI continues to present the assistant as `Dori`.

## Development

- Public packaging and CLI surface are `dori`.
- Internal modules, imports, and tests still use `mnemo8`.
- Boilerplate and onboarding text should refer to Dori unless they are describing the engine explicitly.
