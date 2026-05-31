# Analyze Folder Skill

**Intent**: Use when the user wants to analyze a directory, understand what a project is about, or summarize what a folder/project does.

**Expert behavior:**
- The handler is read-only.
- Inspect only the requested folder, or the current working directory when no folder is stated.
- Do not modify files.
- Prefer local project evidence such as README files, package metadata, lockfiles, config files, and top-level source layout.

**Field guidance:**
- `path`: The directory path to inspect as written by the user (e.g. ".", "backend", "/tmp/app") — omit if the user means the current directory or does not state a path.
- `focus`: A short focus phrase if the user asks for a specific angle (e.g. "what it does", "tech stack", "entry points") — omit if not stated.
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: analyze this directory
Assistant: {"skill": "analyze-folder", "confidence": 0.95, "raw_text": "analyze this directory"}

User: what is this project about?
Assistant: {"skill": "analyze-folder", "confidence": 0.94, "focus": "what the project is about", "raw_text": "what is this project about?"}

User: analize this folder ./api
Assistant: {"skill": "analyze-folder", "confidence": 0.9, "path": "./api", "raw_text": "analize this folder ./api"}
