# Maps Search Skill

**Intent**: Use when the user wants to find a location, get directions, or look up a place.

**Field guidance:**

- `place`: The name or address of the place (e.g. "Louvre Museum Paris", "coffee shops near me")
- `directions_from`: Origin point if directions are requested — omit if not stated
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Where is the Sagrada Familia?
Assistant: {"skill": "maps", "place": "Sagrada Familia Barcelona", "raw_text": "Where is the Sagrada Familia?"}

User: How do I get from Madrid to Barcelona?
Assistant: {"skill": "maps", "place": "Barcelona", "directions_from": "Madrid", "raw_text": "How do I get from Madrid to Barcelona?"}
