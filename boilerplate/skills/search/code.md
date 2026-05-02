# Code Search Skill

**Intent**: Use when the user wants to find code examples, documentation, libraries, packages, or programming solutions.

**Field guidance:**

- `query`: The technical search query (e.g. "Python async http client", "React useState hook example")
- `language`: Programming language if mentioned (e.g. "python", "javascript") — omit if not stated
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Find examples of Python async HTTP requests
Assistant: {"skill": "code", "query": "async HTTP requests", "language": "python", "raw_text": "Find examples of Python async HTTP requests"}

User: How do I center a div in CSS?
Assistant: {"skill": "code", "query": "center a div", "language": "css", "raw_text": "How do I center a div in CSS?"}
