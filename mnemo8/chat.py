import sys
import os
import json
import re
import subprocess
import termios
import tty
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

import ollama

from mnemo8.models import RuntimeState

console = Console()

RETRY_COMMANDS = {"retry", "/retry"}


def get_cursor_row() -> int | None:
    """Query the terminal for the current cursor row (1-indexed)."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        sys.stdout.write("\033[6n")
        sys.stdout.flush()
        response = ""
        while True:
            ch = sys.stdin.read(1)
            response += ch
            if ch == "R":
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    m = re.match(r"\033\[(\d+);\d+R", response)
    return int(m.group(1)) if m else None


def resolve_input(
    user_input: str, last_instruction: str | None
) -> tuple[str | None, str | None]:
    if user_input.strip().lower() in RETRY_COMMANDS:
        return last_instruction, last_instruction
    stripped = user_input.strip()
    return stripped, stripped


def build_system_prompt(state: RuntimeState) -> str:
    prompt = "You are mnemo8, a helpful personal assistant CLI running on the user's terminal.\n"
    if state.agents_content:
        prompt += f"\nHere is information about your agent configuration:\n{state.agents_content}\n"
    if state.skills:
        prompt += "\nHere are your available skills that you should be aware of:\n"
        prompt += "IMPORTANT: If the user asks you to perform an action that matches an available skill, you MUST output a JSON code block with the exact arguments required by the skill.\n"
        for skill in state.skills:
            prompt += f"\n--- Skill: {skill.name} ---\n{skill.content}\n"
    return prompt


def start_chat(state: RuntimeState):
    """Start the TUI chat loop using textual.

    TODO: Implement textual-based TUI to replace prompt_toolkit.
    This is a placeholder for the feat-tui branch implementation.
    """
    # Startup Summary
    console.print(f"\n[bold cyan]mnemo8 Personal Assistant[/bold cyan]")
    console.print(f"Directory: [green]{state.cwd}[/green]")

    if state.agents_content is not None:
        console.print("AGENTS.md [green]loaded[/green]")
    else:
        console.print("AGENTS.md [yellow]not found[/yellow]")

    console.print(f"Skills loaded: [green]{len(state.skills)}[/green]\n")

    system_prompt = build_system_prompt(state)
    messages = [{"role": "system", "content": system_prompt}]
    last_instruction: str | None = None
    retry_row: int | None = None

    # TODO: Replace with textual-based input instead of prompt_toolkit
    console.print("[yellow]TUI implementation coming soon - using textual>=0.52.0[/yellow]")
    console.print("[yellow]Exiting mnemo8...[/yellow]")
