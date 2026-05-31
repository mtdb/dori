# Commit Skill

**Intent**: Use when the user wants Dori to create one or more git commits from the current repository's uncommitted changes.

**Field guidance:**
- `message`: A commit message only if the user explicitly provided one — omit otherwise
- `type`: A conventional commit type only if the user explicitly requested one (e.g. "feat", "fix", "docs") — omit otherwise
- `scope`: A conventional commit scope only if the user explicitly requested one — omit otherwise
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: haz commit de mis cambios
Assistant: {"skill": "commit", "confidence": 0.94, "raw_text": "haz commit de mis cambios"}

User: create commits for the current changes
Assistant: {"skill": "commit", "confidence": 0.95, "raw_text": "create commits for the current changes"}

User: commit this as fix(tui)
Assistant: {"skill": "commit", "confidence": 0.96, "type": "fix", "scope": "tui", "raw_text": "commit this as fix(tui)"}
