# Reminders Skill

**Intent**: Use when the user wants to set a reminder, alarm, or timer.

**Field guidance:**
- `message`: The task only — strip all time expressions and filler words (e.g. "buy milk", not "remind me to buy milk tomorrow")
- `when`: The time expression as spoken (e.g. "tomorrow at 9am", "in 20 minutes")
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Remind me to buy milk in 20 minutes
Assistant: {"skill": "reminders", "confidence": 0.95, "message": "buy milk", "when": "in 20 minutes", "raw_text": "Remind me to buy milk in 20 minutes"}

User: Set an alarm for 7am tomorrow to wake up
Assistant: {"skill": "reminders", "confidence": 0.94, "message": "wake up", "when": "7am tomorrow", "raw_text": "Set an alarm for 7am tomorrow to wake up"}
