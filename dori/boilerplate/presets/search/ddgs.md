# Web Search Skill

**Intent**: Use when the user wants current or externally verifiable information from the internet.

**Expert behavior:**
- Search the public web and answer from retrieved evidence.
- Return a direct answer in English followed by two or three source URLs.
- Do not return a raw list of search results.
- State uncertainty when evidence is insufficient or contradictory.

**Field guidance:**
- `query`: Preserve the factual question while removing search-command filler.
- `freshness`: Use `day`, `week`, `month`, or `year` only when the user requests recent or time-bounded information; omit otherwise.
- `confidence`: Numeric confidence from 0.0 to 1.0.
- `raw_text`: Copy the user's original message verbatim.

**Examples:**
User: When was the Nintendo Switch 2 released?
Assistant: {"skill": "web", "confidence": 0.96, "query": "Nintendo Switch 2 release date", "raw_text": "When was the Nintendo Switch 2 released?"}

User: What is the latest estimate of Spain's population this year?
Assistant: {"skill": "web", "confidence": 0.94, "query": "latest estimate Spain population", "freshness": "year", "raw_text": "What is the latest estimate of Spain's population this year?"}
