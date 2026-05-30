# Git Expert Skill Design

## Summary

Dori should improve the Git skill by treating it as an expert handoff rather
than a brittle command lookup table. For v1, this must stay minimal: no new
agent runtime, no autonomous tools, no repository inspection, and no bundled Git
knowledge base.

The Git expert answers read-only Git questions using local Git documentation as
evidence. If Dori cannot find enough local documentation to answer safely, it
must abstain with a clear fallback instead of guessing.

All project content added for this work must be written in English. Dori may
answer in English even when the user asks in another language, because the
project is optimized for small local LLMs that tend to perform better with
English instructions.

## Goals

- Make the Git skill easier to trigger for normal Git questions.
- Replace the hardcoded answer table with local documentation retrieval.
- Introduce an "expert skill" convention without adding an agent framework.
- Produce natural-language answers with safe steps.
- Prevent hallucinated Git commands, flags, and behavior.
- Keep the project small and local-first.

## Non-goals

- Do not add an `agents/` directory.
- Do not add autonomous tool use.
- Do not inspect the current repository state.
- Do not execute Git commands that modify a repository.
- Do not bundle a curated Git knowledge base.
- Do not build a multi-turn planning agent.
- Do not require Dori to answer in the user's input language.

## Architecture

The v1 design keeps the existing skill/script contract:

```text
User asks a Git question
-> Dori routes to the git skill
-> scripts/git.py receives topic, raw_text, and optional context
-> scripts/git.py retrieves relevant local Git documentation
-> scripts/git.py asks the local LLM to answer using only those fragments
-> scripts/git.py prints either a safe answer or an abstention message
```

`boilerplate/skills/devtools/git.md` becomes a "Git Expert Skill" definition.
This is a convention, not a new runtime primitive. An expert skill is a skill
that answers from local evidence and abstains when evidence is insufficient.

The existing payload shape remains sufficient for v1:

```json
{
  "skill": "git",
  "confidence": 0.9,
  "topic": "rebase",
  "context": "last three commits",
  "raw_text": "How do I squash the last three commits?"
}
```

`topic` is still required, `context` remains optional, and `raw_text` remains
required.

## Local Documentation Retrieval

The Git expert should retrieve local documentation with short timeouts and no
repository side effects. It may run documentation/help commands only.

Preferred source order:

1. `git help <command>` or `git <command> -h` when the topic maps clearly to a
   Git subcommand.
2. `man git-<command>` when the local manpage exists.
3. A local command index such as `git help -a` only to resolve command names,
   not as final answer evidence.

The handler should use a small, explicit command normalization list to avoid
depending on perfect model extraction. Initial v1 commands:

```text
cherry-pick
rebase
stash
branch
tag
remote
reset
revert
merge
log
diff
status
commit
checkout
switch
restore
```

This list is not a knowledge base. It is only a retrieval aid that maps common
questions to local documentation entry points.

If the handler cannot map the question to a command, cannot retrieve local
documentation, or retrieves fragments that are too weak to support an answer, it
must print:

```text
🌿 [Git]: I could not find enough local documentation to answer safely.
```

## Safe Answer Generation

The handler should separate evidence retrieval from answer generation:

- Retrieval collects brief local Git documentation fragments.
- Generation asks the local LLM to convert those fragments into a concise,
  natural-language answer.

The expert prompt must be strict and English-only:

```text
You are a read-only Git expert.
Answer only from the provided local Git documentation fragments.
Do not invent commands, flags, effects, or examples.
If the fragments are not enough, say that you could not find enough local
documentation to answer safely.
Do not run Git commands.
Do not assume the state of the user's repository.
Give safe steps and mention risks only when supported by the documentation.
```

The preferred output shape is stable and simple for small local models:

```text
🌿 [Git - <topic>]
Summary: ...
Steps:
1. ...
2. ...
Safety notes:
- ...
```

If the model call fails, returns an empty answer, or does not follow the
evidence-only contract, the handler should return the abstention message rather
than a best-effort answer.

## Skill Definition Changes

`boilerplate/skills/devtools/git.md` should describe the skill as read-only and
evidence-based.

The intent should cover questions about Git commands, Git workflows, and Git
concepts. The field guidance should keep the payload flat and easy for small
models:

- `topic`: the Git command, workflow, or concept to explain.
- `context`: optional qualifier provided by the user.
- `raw_text`: the user's original message verbatim.

Examples should include varied phrasing and should not require the user to say
"git" explicitly when the intent is clear.

## Testing Strategy

Tests should cover behavior at the script and routing-contract level.

Script-level tests:

- Topic normalization maps common phrasings to supported Git commands.
- Missing or unclear documentation returns the abstention message.
- Documentation retrieval commands are read-only help/man commands.
- The handler does not run repository-mutating Git commands.
- LLM generation failure returns the abstention message.

Boilerplate tests:

- The Git skill remains under the `devtools` router.
- The Git skill examples include `confidence`, `topic`, and `raw_text`.
- The Git skill describes the expert behavior in English.

Conversation tests:

- A Git question can route to the `git` leaf skill.
- Missing `topic` still triggers the existing extraction recovery path.

## Risks And Mitigations

Small local models may still hallucinate during answer generation.

Mitigation: pass only short documentation fragments, use a strict expert prompt,
and prefer abstention when output is empty or unsupported.

Local Git documentation availability varies by operating system and install
method.

Mitigation: treat missing docs as a normal abstention path. Do not add a bundled
knowledge base in v1.

The term "agent" may imply autonomy and tool use.

Mitigation: use "expert skill" for v1. Reserve "agent" for a future runtime
concept if Dori later needs scoped tools, memory, or multi-step execution.

## Open Decisions

No open product decisions remain for v1. Implementation can choose the exact
internal helper names and timeout values, as long as the behavior above remains
unchanged.
