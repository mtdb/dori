# Chat Script Interactions

## Summary

Dori scripts currently support either a one-shot chat invocation or a directly
interactive terminal invocation. Add a small public API that lets the same
script request multiple inputs in both environments without coupling the script
to the conversation engine or Textual.

The first consumer is the `commit` skill. Its existing terminal workflow must
also run as a multi-step workflow inside chat.

## Goals

- Expose three synchronous script functions: `ask`, `confirm`, and `choose`.
- Keep scripts in `~/.dori/scripts` as isolated subprocesses.
- Let chat pause a script, collect the next user message as its answer, and
  resume the same process without another LLM call.
- Preserve direct `dori <skill>` terminal interaction.
- Display ordinary script output before each question and after completion.
- Let `/cancel` terminate an active workflow and restore normal chat behavior.
- Reject interactive workflows clearly in `dori --prompt` mode.

## Non-Goals

- Persisting or restoring workflows across Dori restarts.
- Running multiple workflows concurrently in one conversation.
- Background workflows.
- Streaming script output between interaction boundaries.
- Multiline input, secrets, forms, progress events, or custom widgets.
- Making the private transport protocol part of the public API.

## Public Script API

Add a stable `dori.script` module:

```python
def ask(prompt: str, default: str | None = None) -> str: ...

def confirm(prompt: str, default: bool = False) -> bool: ...

def choose(
    prompt: str,
    choices: list[str] | tuple[str, ...],
    default: str | None = None,
) -> str: ...
```

The functions are synchronous so user scripts remain simple procedural Python.
They validate their arguments before selecting a transport. `choose` requires
at least one unique, non-empty choice, and its default must be one of the
choices.

Expose a public `InteractionUnavailable` exception for environments that cannot
provide follow-up input. Scripts do not import conversation, TUI, or subprocess
implementation details.

## Transport Selection

The API selects one of two transports:

1. When Dori supplies private control-channel environment variables, calls use
   the chat control channel.
2. Otherwise, when stdin is an interactive terminal, calls use terminal
   prompts.

If neither transport is available, an API call raises
`InteractionUnavailable` with guidance to use the TUI or `dori <skill>`.

Direct `dori <skill>` execution inherits the terminal as it does today, so no
new CLI-specific integration is required beyond migrating scripts to the public
API. Running a script manually also uses terminal prompts when stdin is a TTY.

`dori --prompt` must explicitly mark script interaction as unavailable. It must
not unexpectedly consume stdin.

## Private Control Protocol

In chat mode, Dori launches the script with two dedicated pipes:

- A request pipe from the script to Dori.
- A response pipe from Dori to the script.

The parent passes only the numeric file descriptors and a protocol version
through private environment variables. The descriptors are inherited only by
the script process. Normal stdout and stderr retain their existing meanings.

Messages use newline-delimited UTF-8 JSON. Each request contains:

```json
{
  "version": 1,
  "id": 1,
  "type": "choose",
  "prompt": "Commit this group?",
  "choices": ["yes", "no", "type", "scope", "message", "retry", "skip"],
  "default": "yes"
}
```

Each response contains the matching `id` and either an answer or cancellation:

```json
{"version": 1, "id": 1, "answer": "yes"}
```

```json
{"version": 1, "id": 1, "cancelled": true}
```

The protocol is private to Dori. Script authors depend only on `dori.script`.
Malformed messages, mismatched IDs, closed pipes, and unsupported versions
terminate the workflow with a clear error rather than attempting recovery.

## Runtime Architecture

Replace the blocking one-shot chat execution path with a workflow runner that
owns:

- The subprocess.
- Request and response pipes.
- Buffered stdout and stderr.
- The current pending interaction.
- Cancellation and cleanup.

The runner exposes asynchronous operations to start a script, answer its
pending request, cancel it, and wait for its next boundary. A boundary is either
an interaction request or process completion.

The conversation engine owns the active workflow because workflow state is part
of turn execution, not UI rendering. It permits at most one active workflow.
The TUI renders engine results and forwards answers; it does not understand the
pipe protocol or commit-specific state.

One-shot scripts continue to work through the same runner: they simply complete
without sending an interaction request.

## Chat Flow

When the model routes a user request to an interactive skill:

1. The engine starts the subprocess with the control channel enabled.
2. The runner waits until the script requests input or exits.
3. Any stdout produced before that boundary is returned for display.
4. If input is requested, the engine records the pending request and the TUI
   enters workflow mode.
5. The next non-command user submission bypasses conversation history, skill
   routing, payload validation, and the LLM.
6. The engine validates and normalizes the answer, sends it to the script, and
   waits for the next boundary.
7. The cycle repeats until completion, cancellation, or failure.

Workflow answers are visible in the transcript but are not added to the LLM
message history. This prevents later model turns from seeing contextless values
such as `yes` or `3`.

## Answer Validation

Validation happens in Dori before the script resumes:

- `ask` accepts non-empty text. An empty submission selects the default when
  one exists; otherwise Dori repeats the question.
- `confirm` accepts case-insensitive `y`, `yes`, `n`, and `no`. An empty
  submission selects the boolean default.
- `choose` accepts an exact choice, a case-insensitive unambiguous choice, or a
  one-based numeric position. An empty submission selects the default when one
  exists.

Invalid answers produce a short validation message followed by the same
question. They do not resume the subprocess.

The script API also validates responses defensively, so a malformed transport
response cannot silently become a script value.

## Output And Display

Scripts keep using ordinary `print()` and Rich `Console.print()`.

The runner drains stdout concurrently while the script runs to avoid pipe
deadlocks. At each interaction request, accumulated stdout is flushed into the
chat response before the formatted question. Remaining stdout is displayed when
the process exits.

Stderr is retained for diagnostics. On a non-zero exit, Dori reports the
available stderr and clears workflow state. Output already shown at earlier
boundaries remains in the transcript.

The initial skill response retains the existing success label. Follow-up
workflow responses show script output and questions without pretending that a
new skill was routed on every answer.

## Cancellation And Cleanup

While a workflow is active, `/cancel` is handled before ordinary chat commands.
Dori sends a cancellation response when possible, terminates the subprocess,
waits for it to exit, closes all descriptors, and clears active workflow state.
The TUI then reports that the workflow was cancelled and resumes normal input.

Closing the application must perform the same subprocess and descriptor cleanup.
Unexpected process exit, protocol failure, or write failure also clears the
workflow in a `finally` path.

Only `/cancel` is added as workflow control in this version. `/retry`, `/clear`,
translation, and edit-last-message actions must not operate on a pending
workflow answer.

## Inline Mode

`dori --prompt` remains a single-turn interface. It may run scripts that finish
without requesting input. If a script calls the public interaction API, Dori
terminates that execution and prints a clear message such as:

```text
This workflow needs follow-up input. Use the Dori TUI or run `dori commit`.
```

Inline mode never falls back to reading stdin.

## Commit Skill Migration

The commit workflow will replace direct Rich input calls with the public API:

- `Confirm.ask` becomes `confirm`.
- Free-text `Prompt.ask` becomes `ask`.
- Choice prompts and commit-type selection become `choose`.

Existing `Console.print()` calls and Git operations remain unchanged. The
workflow receives initial `message`, `type`, and `scope` payload values when
provided and may use them as initial values without changing the generic
interaction API.

The `commit.py` entry point runs the same workflow for both chat and CLI payloads
instead of returning the current instruction to use `dori commit`.

## Error Handling

- Missing script: preserve the current missing-handler error.
- Invalid public API arguments: raise `ValueError` before sending a request.
- Interaction unavailable: raise `InteractionUnavailable` with actionable
  guidance.
- Invalid user answer: keep the workflow pending and repeat the question.
- Protocol violation: terminate the workflow and report a concise internal
  interaction error.
- Script non-zero exit: show stderr and clear the workflow.
- TUI shutdown or `/cancel`: terminate and reap the child process.

## Testing

Unit tests will cover:

- `ask`, `confirm`, and `choose` terminal behavior.
- Public API argument validation.
- Control-channel request and response serialization.
- `InteractionUnavailable` outside a TTY or enabled control channel.
- Answer parsing, defaults, invalid answers, and repeated questions.
- A subprocess pausing and resuming across multiple requests.
- Stdout flushing before questions and at completion.
- Non-zero exits, malformed protocol messages, cancellation, and descriptor
  cleanup.
- Conversation history excluding workflow answers.
- TUI forwarding answers without calling the LLM.
- `dori --prompt` allowing non-interactive scripts and rejecting interactive
  ones.
- The commit workflow using the same API in direct CLI and chat execution.

Existing one-shot skill, direct CLI dispatch, and commit workflow tests remain
as regression coverage.

## Documentation

Update the runtime and skill-authoring documentation to describe `dori.script`
as the supported interaction boundary. Examples should remain small and avoid
exposing environment variables, file descriptors, or protocol JSON to users
writing scripts.
