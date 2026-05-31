# News Search Skill

**Intent**: Use when the user wants to find recent news, current events, or latest updates on a topic.

**Field guidance:**

- `query`: The news topic (e.g. "AI regulation EU", "earthquake Japan")
- `since`: Time filter if mentioned (e.g. "today", "this week", "last 24 hours") — omit if not stated
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: What's the latest news on the Ukraine war?
Assistant: {"skill": "news", "confidence": 0.94, "query": "Ukraine war", "since": "today", "raw_text": "What's the latest news on the Ukraine war?"}

User: Find recent articles about climate change
Assistant: {"skill": "news", "confidence": 0.9, "query": "climate change", "raw_text": "Find recent articles about climate change"}
