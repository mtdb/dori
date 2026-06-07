# D-Bus Reminders Preset

**Intent**: Use when the user wants a local desktop reminder through D-Bus notifications.

**Runtime guidance:**
- Requires `notify-send` for real reminder scheduling.
- Supports only relative times in seconds, minutes, or hours.
- Use `dry_run` only for tests or previews where no desktop notification should be scheduled.

**Field guidance:**
- `message`: The task only — strip all time expressions and filler words (e.g. "drink water", not "remind me to drink water")
- `when`: A supported relative time (e.g. "in 20 minutes", "in 2 hours", "in 30 seconds")
- `confidence`: Numeric confidence from 0.0 to 1.0
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: Remind me to drink water in 20 minutes
Assistant: {"skill": "reminders", "confidence": 0.95, "message": "drink water", "when": "in 20 minutes", "raw_text": "Remind me to drink water in 20 minutes"}

User: Set a timer to stretch in 2 hours
Assistant: {"skill": "reminders", "confidence": 0.94, "message": "stretch", "when": "in 2 hours", "raw_text": "Set a timer to stretch in 2 hours"}
