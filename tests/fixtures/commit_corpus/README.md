# Commit message evaluation corpus

Fixtures for `tests/test_commit_llm_eval.py`, which evaluates the commit
message generation in `boilerplate/scripts/_commit_workflow.py` against the
real local model (`llama3.1:8b`, `seed=42`, `temperature=0`).

## Sources

- `angular-*`: real commits from [angular/angular](https://github.com/angular/angular),
  chosen because the project follows conventional commits rigorously.
- `dori-*`: real commits from this repository. Their original messages vary
  in quality, so each case carries a hand-curated `curated_subject` used as
  the human reference (the git history itself is never rewritten).

Cases are picked so that the diff fits within `MAX_PROMPT_DIFF_CHARS` and
the message is genuinely derivable from the diff alone.

## Expectations model

Exact-match against the original message is impossible for a small local
model, so each fixture curates what "good enough" means:

- `expected_types`: acceptable conventional commit types. Multiple types are
  listed when the diff alone is honestly ambiguous (e.g. a hardening change
  with no tests reads as `fix`, `refactor`, or `perf`).
- `expected_keywords`: groups of alternatives; the generated subject+body
  must contain at least one alternative from **every** group
  (case-insensitive substring).
- `expected_scopes`: informational only. Project scopes are internal
  conventions a model cannot infer from a diff, so they are never asserted.

## Regenerating

```
python tests/fixtures/commit_corpus/generate.py
```

Requires network access (GitHub API; set `GITHUB_TOKEN` to avoid the
unauthenticated rate limit) and a checkout of this repository containing the
referenced dori SHAs. Curated expectations live in `generate.py` — edit them
there, not in the JSON files.
