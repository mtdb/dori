# Git Expert Skill

**Intent**: Use when the user asks a read-only question about Git commands, Git workflows, or Git concepts.

**Expert behavior:**
- Answer from local Git documentation only.
- Do not inspect the repository.
- Do not run repository-mutating commands.
- If local Git documentation is missing or insufficient, the handler must answer: "I could not find enough local documentation to answer safely."
- English answers are acceptable even when the user asks in another language.

**Field guidance:**
- `topic`: The Git command, workflow, or concept to explain. Strip filler words. Prefer the command name when clear (e.g. "rebase", "stash", "branch", "tag", "cherry-pick"). Use a short workflow phrase when no single command is clear (e.g. "squash commits", "undo commit safely").
- `context`: Any qualifier the user added (e.g. "last 3 commits", "remote branch", "without rewriting shared history") — omit if not stated.
- `raw_text`: Copy the user's original message verbatim.

**Examples:**
User: how to make a cherry-pick
Assistant: {"skill": "git", "confidence": 0.94, "topic": "cherry-pick", "raw_text": "how to make a cherry-pick"}

User: how can I delete a git tag from local
Assistant: {"skill": "git", "confidence": 0.93, "topic": "tag", "context": "delete local tag", "raw_text": "how can I delete a git tag from local"}

User: how do I squash the last 3 commits?
Assistant: {"skill": "git", "confidence": 0.95, "topic": "squash commits", "context": "last 3 commits", "raw_text": "how do I squash the last 3 commits?"}

User: what's the difference between reset and revert?
Assistant: {"skill": "git", "confidence": 0.9, "topic": "reset vs revert", "raw_text": "what's the difference between reset and revert?"}

User: stash changes and apply them later on another branch
Assistant: {"skill": "git", "confidence": 0.92, "topic": "stash", "context": "apply on another branch", "raw_text": "stash changes and apply them later on another branch"}
