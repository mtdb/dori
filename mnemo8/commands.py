import os
from pathlib import Path
from rich.console import Console

console = Console()

DEFAULT_AGENTS_MD = """# mnemo8 Agents

## Noctis (Default)

You are Noctis, my locally-running personal assistant. 
Your primary purpose is to help me organize my thoughts, manage my notes, and navigate the files in this directory.

**Your Identity & Tone:**
- You are concise, sharp, and highly analytical.
- You provide practical, direct answers without unnecessary fluff or robotic filler.
- You act as a reliable sounding board for my ideas and tasks.
- You prioritize the local context of my files and workflows over generic web knowledge.
"""

DEFAULT_SKILL_MD = """# Reminder Skill
---
name: reminder
description: "Create and manage short reminders, todo items, and calendar events. Use when: add/edit/list/remove reminders. Optimized for small LLMs."
user-invocable: true
applyTo: ["**/*"]
version: "0.1.0"
---

# Reminder Skill

Compact guidance for workspace assistants focused on organization tasks (reminders, todos, short calendar events). Keep prompts and outputs minimal for small models.

Usage:
- Trigger with: "add reminder", "list reminders", "create event"
- Response style: one-line confirmation plus concise bullet details
- Follow-ups: ask only if the time/date or recipient is ambiguous

Example:
- Add: "Add reminder: Pay rent tomorrow 9am"
    - Reply: "Reminder added — Pay rent — Tomorrow 09:00"
"""

def init_workspace(cwd: str):
    """Initializes the current directory with default mnemo8 files."""
    root_path = Path(cwd)
    agents_file = root_path / "AGENTS.md"
    skills_dir = root_path / "skills"
    reminders_skill_file = skills_dir / "reminders.md"

    # Create AGENTS.md
    if not agents_file.exists():
        agents_file.write_text(DEFAULT_AGENTS_MD, encoding="utf-8")
        console.print(f"[green]Created[/green] {agents_file.name}")
    else:
        console.print(f"[yellow]Skipped[/yellow] {agents_file.name} (already exists)")

    # Create skills directory and reminders skill
    if not skills_dir.exists():
        skills_dir.mkdir()
        console.print(f"[green]Created[/green] skills/ directory")
    
    if not reminders_skill_file.exists():
        reminders_skill_file.write_text(DEFAULT_SKILL_MD, encoding="utf-8")
        console.print(f"[green]Created[/green] {reminders_skill_file.relative_to(root_path)}")
    else:
        console.print(f"[yellow]Skipped[/yellow] {reminders_skill_file.relative_to(root_path)} (already exists)")
        
    console.print("\n[bold cyan]mnemo8 workspace initialized successfully![/bold cyan]")
