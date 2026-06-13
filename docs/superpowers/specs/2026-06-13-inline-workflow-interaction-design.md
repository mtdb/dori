# Inline Workflow Interaction Design

## Goal

Allow `dori -p` to complete any skill workflow that uses `dori.script.ask`,
`confirm`, or `choose` when the command is attached to an interactive terminal.
When stdin is not a TTY, the command must stop safely with a clear error instead
of executing a pending action or consuming piped input.

## Architecture

The existing interaction protocol remains the single mechanism for communication
between skill scripts and Dori:

- `dori.script` emits structured interaction requests.
- `WorkflowRunner` transports requests and responses over its file descriptors.
- `ConversationEngine` owns the active workflow and exposes
  `answer_workflow()` and `cancel_workflow()`.
- A new inline workflow driver in the CLI owns terminal rendering and input.

The driver must not interpret or validate answers itself. It passes raw terminal
input to `ConversationEngine.answer_workflow()`, which delegates normalization
and validation to the existing workflow layer.

## Inline Data Flow

`_run_inline()` creates one event loop and one `ConversationEngine` with script
interaction enabled. The complete workflow runs inside that event loop:

1. Send the initial prompt with `engine.send()`.
2. Print the returned display text.
3. If no workflow is pending, finish.
4. If a workflow is pending, verify that stdin is a TTY.
5. Read one terminal answer and pass it to `engine.answer_workflow()`.
6. Print the next response and repeat until the workflow finishes.

Keeping all steps in one `asyncio.run()` call is required because the active
`WorkflowRunner`, subprocess, queues, and tasks belong to the event loop where
they were created.

## Terminal Behavior

The existing `ConversationEngine` request formatting is used for all request
types:

- `ask` displays its prompt and optional default.
- `confirm` displays its prompt and yes/no default.
- `choose` displays numbered choices and its optional default.

The CLI reads answers from stdin only when `sys.stdin.isatty()` is true. It does
not support scripted answers from pipes.

Invalid answers remain in the workflow. The engine returns the validation error
and repeats the pending request, allowing the user to try again.

## Cancellation And Errors

If a workflow requests input while stdin is not a TTY, the driver cancels and
closes the workflow, then exits with a concise error explaining that inline
interaction requires a terminal.

EOF and `KeyboardInterrupt` are treated as user cancellation. The driver asks
the engine to cancel the active workflow and closes it before returning a
non-zero exit status.

Unexpected errors also close the engine before they are surfaced. Cleanup must
not leave a skill subprocess waiting for an interaction response.

## Scope

This change applies generically to every skill using the public interaction API.
No reminder-specific or calendar-specific branches are introduced.

Direct skill execution through `dori <skill-name>` remains unchanged because
those scripts already inherit the terminal and use the direct terminal fallback
in `dori.script`.

The TUI remains unchanged and continues to answer workflow requests through its
existing chat interaction.

## Testing

Tests will verify:

- Inline mode enables the workflow interaction protocol.
- `ask`, `confirm`, and `choose` requests can complete through terminal input.
- Multiple sequential requests complete in one inline invocation.
- Invalid answers display an error and permit another attempt.
- A pending request with non-TTY stdin is cancelled and fails clearly.
- EOF and `KeyboardInterrupt` cancel and close the workflow.
- A non-interactive skill still prints its result and exits normally.
- The reminder regression is covered by an inline workflow integration test.

The existing workflow, script API, TUI, and CLI test suites must continue to
pass.
