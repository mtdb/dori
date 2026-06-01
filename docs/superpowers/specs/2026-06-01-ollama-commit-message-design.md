# Ollama Commit Message Suggestions Design

## Goal

Improve `dori commit` so suggested commit messages describe the actual change instead
of defaulting to generic subjects such as `update <folder>`.

The workflow remains interactive: Dori suggests a message, shows it to the user, and
lets the user accept, skip, change type, change scope, or manually edit the message
before committing.

## Scope

This change only uses local Ollama. It does not add remote LLM providers, API keys, or
provider configuration.

The existing deterministic workflow stays responsible for:

- finding the git repository
- scanning changed files
- grouping files into commits
- detecting commit type and scope
- deciding whether an amend is safe to offer
- staging and committing selected groups

Ollama only improves the suggested commit message for each already-detected group.

## User Flow

For each commit group, Dori will:

1. Show the group as it does today.
2. Generate the current heuristic commit message as a fallback.
3. Ask Ollama for a better conventional commit message using the group metadata and
   trimmed diffs.
4. Validate the model output.
5. Show the chosen suggestion in the existing review prompt.
6. Allow the user to accept, skip, change type, change scope, or manually edit the
   message before committing.

If Ollama is unavailable, errors, or returns invalid output, Dori will keep the
heuristic message and print a short note explaining that the local model suggestion
was skipped.

## Prompt Inputs

The prompt will include:

- detected conventional commit type
- detected scope
- changed file paths
- file statuses
- old path for renames
- trimmed diff snippets already collected by `scan_changes`
- instructions to output only the commit message

The prompt will ask for a concise conventional commit message in imperative mood and
will explicitly reject generic subjects such as `update folder`, `update files`, or
`update project`.

## Output Rules

The model response must be a commit message only:

- no markdown code fences
- no explanations
- no bullet list outside an optional commit body
- first line must be a conventional commit subject
- first line must use the detected type when available
- first line must use the detected scope when available
- first line should include the configured gitmoji for the type when one exists

If the model violates these rules, Dori will use the fallback message.

## Components

`build_commit_message(group)` remains the deterministic fallback.

New helper responsibilities in `mnemo8.commit_workflow`:

- build an Ollama prompt from a `CommitGroup`
- call local Ollama using the existing default model
- sanitize and validate the response
- return either a valid LLM message or `None`
- choose the LLM message when valid, otherwise the fallback

The implementation should keep the Ollama import lazy so basic commit behavior still
works when the Python package or local service is unavailable.

## Error Handling

Ollama failures are non-fatal. The commit workflow must continue with the heuristic
message when:

- the `ollama` package cannot be imported
- the local Ollama service is not running
- the model call raises an exception
- the model returns an empty response
- the model returns markdown, explanations, or a malformed subject

## Testing

Unit tests will cover:

- prompt construction includes type, scope, file status, paths, and diff snippets
- valid Ollama responses are accepted
- markdown or explanatory responses are rejected
- type or scope mismatches are rejected when those values were detected
- Ollama failures fall back to `build_commit_message`
- the review loop uses the LLM suggestion while preserving manual message editing

