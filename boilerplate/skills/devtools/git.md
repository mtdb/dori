# Git Skill

**Intent**: Use when the user asks how to do something with git, wants to know a git command, or asks a question about git workflows (e.g. cherry-pick, rebase, stash, reset, merge).

**Field guidance:**
- `topic`: The git action and object — strip the word "git", question words, and filler. For named operations use the operation name (e.g. "cherry-pick", "rebase", "stash"). For action+object questions combine them (e.g. "delete tag", "create branch", "list remotes", "push tag"). Always lowercase.
- `context`: Any qualifier the user added (e.g. "from local only", "without committing", "last 3 commits") — omit if not stated
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: how to make a cherry-pick
Assistant: {"skill": "git", "topic": "cherry-pick", "raw_text": "how to make a cherry-pick"}

User: how can I delete a git tag from local
Assistant: {"skill": "git", "topic": "delete tag", "context": "local only", "raw_text": "how can I delete a git tag from local"}

User: how do I squash the last 3 commits?
Assistant: {"skill": "git", "topic": "squash commits", "context": "last 3 commits", "raw_text": "how do I squash the last 3 commits?"}

User: what's the difference between git reset and git revert?
Assistant: {"skill": "git", "topic": "reset vs revert", "raw_text": "what's the difference between git reset and git revert?"}

User: how to stash changes and apply them later on another branch
Assistant: {"skill": "git", "topic": "stash", "context": "apply on another branch", "raw_text": "how to stash changes and apply them later on another branch"}

User: how do I rename a branch?
Assistant: {"skill": "git", "topic": "rename branch", "raw_text": "how do I rename a branch?"}

User: how to delete a remote branch
Assistant: {"skill": "git", "topic": "delete branch", "context": "remote", "raw_text": "how to delete a remote branch"}
