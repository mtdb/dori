import sys
import os
import json
import re
import subprocess
import termios
import tty
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
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
    """Start the REPL chat loop."""

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
    history = InMemoryHistory()

    # REPL Loop
    while True:
        try:
            # User input
            current_row = get_cursor_row()
            user_input = pt_prompt(ANSI("\033[1;32mYou\033[0m: "), history=history)

            # Check for exit commands
            if user_input.strip().lower() in ["exit", "quit"]:
                console.print("\n[yellow]Exiting mnemo8...[/yellow]")
                break

            if not user_input.strip():
                continue

            resolved, last_instruction = resolve_input(user_input, last_instruction)
            if resolved is None:
                console.print("[yellow]No previous instruction to retry.[/yellow]")
                continue
            if resolved != user_input.strip():
                if retry_row is not None:
                    sys.stdout.write(f"\033[{retry_row};1H\033[J")
                    sys.stdout.flush()
                if (
                    len(messages) >= 3
                    and messages[-1]["role"] == "assistant"
                    and messages[-2]["role"] == "user"
                ):
                    messages.pop()
                    messages.pop()
            else:
                retry_row = current_row
            user_input = resolved

            messages.append({"role": "user", "content": user_input})

            with console.status("[bold cyan]Thinking...[/bold cyan]"):
                response = ollama.chat(model="llama3.1:8b", messages=messages)

            assistant_content = response["message"]["content"]
            messages.append({"role": "assistant", "content": assistant_content})

            console.print("\n[bold cyan]mnemo8[/bold cyan] >")

            # Try to parse as JSON or extract JSON block
            parsed_json = None

            try:
                parsed_json = json.loads(assistant_content)
            except json.JSONDecodeError:
                match = re.search(
                    r"```(?:json)?\s*(\{.*?\})\s*```", assistant_content, re.DOTALL
                )
                if match:
                    try:
                        parsed_json = json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass

            if parsed_json and isinstance(parsed_json, dict) and "skill" in parsed_json:
                skill_name = parsed_json["skill"]
                mnemo_home = os.path.expanduser("~/.mnemo8")
                script_path = os.path.join(mnemo_home, "scripts", f"{skill_name}.py")

                if os.path.isfile(script_path):
                    try:
                        result = subprocess.run(
                            [sys.executable, script_path, json.dumps(parsed_json)],
                            capture_output=True,
                            text=True,
                            check=True,
                        )
                        console.print(
                            f"[bold green]Skill Executed:[/bold green] {skill_name}"
                        )
                        console.print(result.stdout.strip())
                    except subprocess.CalledProcessError as e:
                        console.print(
                            f"[red]Skill script '{skill_name}' failed:[/red]\n{e.stderr.strip()}"
                        )
                else:
                    console.print(
                        f"[red]Error:[/red] Script for skill '{skill_name}' not found at {script_path}"
                    )
            else:
                console.print(Markdown(assistant_content))

            console.print()

        except (KeyboardInterrupt, EOFError):
            console.print("\n\n[yellow]Exiting mnemo8...[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]An error occurred: {e}[/red]")
