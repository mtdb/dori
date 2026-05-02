# Image Search Skill

**Intent**: Use when the user wants to find images, photos, pictures, or visual references.

**Field guidance:**

- `query`: The image search query (e.g. "sunset over mountains", "logo for Python")
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Find photos of the Eiffel Tower at night
Assistant: {"skill": "images", "query": "Eiffel Tower at night", "raw_text": "Find photos of the Eiffel Tower at night"}

User: Show me pictures of golden retrievers
Assistant: {"skill": "images", "query": "golden retrievers", "raw_text": "Show me pictures of golden retrievers"}
