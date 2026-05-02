# News Search Skill

**Intent**: Use when the user wants to find recent news, current events, or latest updates on a topic.

**Field guidance:**

- `query`: The news topic (e.g. "AI regulation EU", "earthquake Japan")
- `since`: Time filter if mentioned (e.g. "today", "this week", "last 24 hours") — omit if not stated
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: What's the latest news on the Ukraine war?
Assistant: {"skill": "news", "query": "Ukraine war", "since": "today", "raw_text": "What's the latest news on the Ukraine war?"}

User: Find recent articles about climate change
Assistant: {"skill": "news", "query": "climate change", "raw_text": "Find recent articles about climate change"}
