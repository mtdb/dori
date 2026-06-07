# Calendar Skill

**Intent**: Use when the user wants to add an event, schedule a meeting, block time, or check their calendar.

**Field guidance:**
- `title`: The event name only — strip filler words (e.g. "team standup", not "add a meeting for team standup")
- `when`: The date/time expression as spoken (e.g. "tomorrow at 3pm", "next Monday")
- `duration`: How long the event lasts, if mentioned (e.g. "1 hour", "30 minutes") — omit if not stated
- `location`: Where the event takes place, if mentioned — omit if not stated
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Schedule a dentist appointment for Friday at 10am
Assistant: {"skill": "calendar", "confidence": 0.94, "title": "dentist appointment", "when": "Friday at 10am", "raw_text": "Schedule a dentist appointment for Friday at 10am"}

User: Add a 1-hour team standup every Monday at 9am in the conference room
Assistant: {"skill": "calendar", "confidence": 0.93, "title": "team standup", "when": "every Monday at 9am", "duration": "1 hour", "location": "conference room", "raw_text": "Add a 1-hour team standup every Monday at 9am in the conference room"}
