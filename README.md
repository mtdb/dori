# mnemo8 — local-first, folder-native agent runtime

Mnemo8 turns any filesystem directory into a self-contained personal agent runtime optimized for local and small LLMs. It discovers declarative `skills/`, reads `AGENTS.md` behavioral instructions, and routes natural language into deterministic tool execution.

## Why this project exists

- Privacy & control: runs without default cloud dependency.
- Low resource targets: designed to work well with compact, local models.
- Portability: move a folder and you move the assistant and its memory.
- Reproducibility: declarative skills and explicit tool execution reduce surprises.

## Local / small-LLM optimizations

- Short, structured prompts (templates + few-shot examples) to fit small context windows.
- Declarative skill schemas (IO types) to minimize LLM grounding work.
- Deterministic tool runtime for side effects — LLM suggests, tools execute.
- Local embeddings / caching in `.mnemo8/` to avoid re-computation and speed retrieval.
- Prefer explicit step-by-step plans that small models can follow reliably.

## Quickstart

1. Ensure Python 3.11+ is installed.
2. From the repository root, install in editable mode:

```bash
pip install -e .
```

3. Run the assistant from any directory:

```bash
mnemo8
```

The CLI will look for an `AGENTS.md` file and a `skills/` folder in the current working directory.

## How it works (overview)

Mnemo8 is layered for clarity and safety:

1. Cognitive layer — small/local LLMs provide intent interpretation and plan generation.
2. Skill layer — declarative `skills/` that define triggers, input/output schemas, and execution endpoints.
3. Context layer — project-bound memory and configuration (`AGENTS.md`, `.mnemo8/`).
4. Execution layer — deterministic tool runtime that enforces validation and performs side effects.

## Directory layout

Every Mnemo8 instance is self-contained in a folder:

```
project/
├── AGENTS.md        # system instructions / persona
├── skills/          # declarative skill files (intent, schema, handler)
└── .mnemo8/         # runtime state, cache, embeddings
```

## Authoring notes (skills & agents)

- `AGENTS.md`: short system-level instructions and routing hints for the local model.
- `skills/`: each skill is a small, declarative file describing:
  - intent patterns or examples
  - input and output schema (prefer simple JSON schema)
  - execution endpoint (local function name or external connector)

## Best practices for small models

- Keep system prompts concise and explicit.
- Provide 1–3 few-shot examples per intent.
- Use schemas to reduce free-form generation and enable validation.
- Break complex workflows into chained skills that call tools deterministically.

## Runtime behavior

On startup (`mnemo8`): detect CWD → load `AGENTS.md` → register `skills/` → init `.mnemo8/` → start interactive session → route user intents to skills and tools.

## Development

Install editable for fast iteration:

```bash
pip install -e .
```

Edit code in `mnemo8/`, restart the CLI to pick up changes.

## Examples & next steps

- To try the MVP, create a folder with an `AGENTS.md` and a tiny `skills/` file and run `mnemo8`.
- If you'd like, I can add a minimal example `skills/` folder and an example `AGENTS.md` to this repo — tell me and I will add it.

## License & Contributing

Contributions, issues and suggestions are welcome. Open a PR or an issue to start a discussion.

—

This single-file README is intended to give a clear, immediate view of the project and highlight Mnemo8's emphasis on local and small-LLM usage. For any additions (examples, demos, tests), I can add them directly into this repository on request.
