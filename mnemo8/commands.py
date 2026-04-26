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

DEFAULT_SKILL_MD = """# Example Skill

This is an example skill. Use this file to define specific workflows, formatting rules, or tools the assistant should use for particular tasks.

## Usage

Describe when and how the assistant should apply this skill.
"""

def init_workspace(cwd: str):
    """Initializes the current directory with default mnemo8 files."""
    root_path = Path(cwd)
    agents_file = root_path / "AGENTS.md"
    skills_dir = root_path / "skills"
    example_skill_file = skills_dir / "example.md"

    # Create AGENTS.md
    if not agents_file.exists():
        agents_file.write_text(DEFAULT_AGENTS_MD, encoding="utf-8")
        console.print(f"[green]Created[/green] {agents_file.name}")
    else:
        console.print(f"[yellow]Skipped[/yellow] {agents_file.name} (already exists)")

    # Create skills directory and example skill
    if not skills_dir.exists():
        skills_dir.mkdir()
        console.print(f"[green]Created[/green] skills/ directory")
    
    if not example_skill_file.exists():
        example_skill_file.write_text(DEFAULT_SKILL_MD, encoding="utf-8")
        console.print(f"[green]Created[/green] {example_skill_file.relative_to(root_path)}")
    else:
        console.print(f"[yellow]Skipped[/yellow] {example_skill_file.relative_to(root_path)} (already exists)")
        
    console.print("\n[bold cyan]mnemo8 workspace initialized successfully![/bold cyan]")
