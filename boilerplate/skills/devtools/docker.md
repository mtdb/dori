# Docker Skill

**Intent**: Use when the user asks a question about Docker, such as how to run, stop, remove, or inspect containers or images.

**Field guidance:**
- `question`: The core Docker question — strip conversational filler (e.g. "remove a container", not "how do I remove a docker container?")
- `raw_text`: Copy the user's original message verbatim

**Examples:**
User: How do I remove a docker container?
Assistant: {"skill": "docker", "question": "remove a container", "raw_text": "How do I remove a docker container?"}

User: How can I list all running containers?
Assistant: {"skill": "docker", "question": "list running containers", "raw_text": "How can I list all running containers?"}

User: What command stops all containers?
Assistant: {"skill": "docker", "question": "stop all containers", "raw_text": "What command stops all containers?"}
