# Web Search Skill

**Intent**: Use when the user wants to search the internet, look something up, or find information online.

**Field guidance:**

- `query`: The search query — strip filler words (e.g. "latest Python release", not "search for the latest Python release")
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Search for the latest Python release
Assistant: {"skill": "web", "confidence": 0.95, "query": "latest Python release", "raw_text": "Search for the latest Python release"}

User: Look up the weather in Madrid tomorrow
Assistant: {"skill": "web", "confidence": 0.91, "query": "weather in Madrid tomorrow", "raw_text": "Look up the weather in Madrid tomorrow"}
