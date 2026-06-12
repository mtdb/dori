# Conservative Commit Grouping Design

## Goal

Improve `dori commit` so it creates one commit per logical change instead of
splitting related files because they live in different top-level directories.

The workflow should prefer fewer meaningful commits, automatically split only
when there is strong evidence that changes are independent, and ask the user
when a proposed split is uncertain.

Recent commit subjects may guide commit-message style, but must not influence
file grouping.

## Scope

This change covers:

- deterministic grouping of changed files
- confidence classification for proposed multi-group results
- one interactive decision for uncertain grouping
- recent commit subjects as untrusted message-style examples
- tests for grouping, interaction, and prompt construction

It does not add model-driven grouping, repository mutation before user approval,
configuration options, or new commit-message providers.

## Design Principles

- A logical change should be reverted as one unit.
- Tests, configuration, and supporting files belong with the behavior they
  enable when there is evidence of a relationship.
- Two changed files should remain together unless strong evidence shows they
  are independent.
- Directory location alone is not enough evidence to split files.
- Automatic splitting requires stronger evidence than automatic merging.
- Ambiguous grouping is a user decision, not a hidden heuristic.

## Grouping Model

Grouping will use a deterministic relationship graph.

Each changed file is a node. Strong relationship signals add edges between
files. Connected nodes become candidate commit groups.

### Strong Relationship Signals

Files stay in the same candidate group when one or more of these signals apply:

- Source and test names match after removing conventions such as `test_` and
  `_test`.
- A test path and source path share the same meaningful module or feature name.
- Files share a specific feature or module directory after ignoring structural
  roots such as `src`, `app`, `lib`, `tests`, and `test`.
- A changed source or test diff references a changed configuration filename,
  setting name, environment variable, or configuration key.
- A rename's old and new paths are treated as one change and remain with other
  modifications to the same module.
- Changed files directly reference one another by module name, filename stem,
  import path, or a distinctive identifier found in their diffs.

Signals must be based on normalized paths and the bounded diff snippets already
collected by `scan_changes`. The implementation must not read arbitrary
repository files or invoke Ollama for grouping.

### Strong Independence Signals

Dori may automatically split candidate groups only when their concerns are
clearly independent. Examples include:

- documentation-only changes unrelated to changed application identifiers
- CI-only changes unrelated to the changed application or build configuration
- separate feature or module roots with no path, stem, identifier, or diff
  references connecting them

File category alone is not sufficient to prove independence. In particular,
tests and configuration must not be separated from application code merely
because they are tests or configuration.

### Conservative Defaults

- Zero changed files produces no groups.
- One changed file produces one group.
- Two changed files produce one group unless strong independence is detected.
- If all files are connected by strong relationship signals, Dori produces one
  group.
- If multiple groups have strong independence evidence between them, Dori uses
  the proposed split automatically.
- If multiple candidate groups remain without strong independence evidence, the
  proposal is uncertain and Dori asks the user.

## Grouping Result

The grouping function will return structured metadata rather than only a nested
list. The result contains:

- the proposed file groups
- whether the proposal is `certain` or `uncertain`
- short deterministic reasons supporting the split

This metadata is used only for review and tests. Commit execution continues to
operate on `CommitGroup` instances.

## Uncertain Grouping Flow

When an uncertain result contains multiple proposed groups, Dori shows all
groups before generating individual commit messages:

```text
Grouping is uncertain:

Group 1
  ~ src/payments/service.py
  ~ tests/payments/test_service.py

Group 2
  ~ config/settings.py

How should these changes be committed?
  1. Use proposed groups
  2. Create one commit
```

`Create one commit` is the default. This matches the conservative preference
for avoiding accidental over-splitting.

If the user chooses the proposed groups, the existing per-group review loop
continues unchanged. If the user chooses one commit, Dori combines every changed
file into a single `CommitGroup`, then detects its type and scope and starts the
normal review loop.

The question is asked once per `dori commit` run, not once per group.

## Commit Message Style Context

`scan_changes` already loads the latest five commit subjects. These subjects
will be passed to the commit-message prompt as untrusted style examples.

The prompt will state that recent subjects may guide:

- common conventional commit types
- common scopes
- capitalization and wording style
- typical subject specificity
- whether the repository commonly uses a short body

The prompt will also state that history must not override the detected type or
scope and must not be treated as instructions. Recent subjects are not passed
to the grouping function.

When there is no commit history, prompt behavior remains unchanged apart from
omitting the style-example section.

## Components

The commit workflow will separate these responsibilities:

- normalize paths and extract relationship identifiers
- score or classify pairwise file relationships
- build connected candidate groups
- classify a multi-group proposal as certain or uncertain
- render and resolve the uncertain-grouping choice
- build commit-message prompts with optional recent-subject context

`run_interactive` remains responsible for orchestration:

1. scan changes and recent subjects
2. compute the grouping result
3. resolve uncertain grouping once
4. create `CommitGroup` instances
5. perform the existing amend and per-group review flows
6. stage and commit approved groups

## Error Handling

- Grouping analysis is deterministic and must not fail because Ollama is
  unavailable.
- Missing or empty diffs reduce available relationship evidence but do not stop
  the workflow.
- If relationship analysis cannot establish independence, the result is
  uncertain rather than automatically split.
- If interactive input is unavailable, existing script interaction behavior
  applies; the workflow reports that interaction is unavailable instead of
  choosing a split silently.
- Invalid recent commit subjects are treated as plain untrusted text and do not
  affect validation rules.

## Testing

Unit tests will cover:

- a feature and its matching test remain in one group
- source and test files in different top-level directories remain together
- configuration remains with code that references its key or setting
- two ambiguous changed files default to one proposed group
- unrelated documentation and application changes split with strong evidence
- unrelated feature roots split when no relationship signal connects them
- uncertain multi-group proposals include reasons and require a choice
- choosing one commit combines all files before type and scope detection
- choosing proposed groups preserves the candidate groups
- the grouping question is asked only once
- recent commit subjects appear in the message prompt as untrusted style
  examples
- recent commit subjects do not enter or change grouping results
- empty history omits the style-example section

Existing tests for staging, hooks, amend behavior, message validation, and
per-group review must continue to pass.

## Success Criteria

- Related implementation, test, and configuration files are not split solely
  because of their directory or file category.
- Two-file changes stay together unless their independence is clear.
- Dori automatically splits only when deterministic evidence supports the
  separation.
- Users can combine uncertain proposed groups with one choice before commit
  review begins.
- Recent commit history improves message consistency without affecting grouping
  or weakening message validation.
