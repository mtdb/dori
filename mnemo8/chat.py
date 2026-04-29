import sys
import os
import json
import re
import subprocess
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown

import ollama

from mnemo8.models import RuntimeState

console = Console()


def build_system_prompt(state: RuntimeState) -> str:
    prompt = "You are mnemo8, a helpful personal assistant CLI running on the user's terminal.\n"
    if state.agents_content:
        prompt += f"\nHere is information about available agents that might be relevant:\n{state.agents_content}\n"
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

    # REPL Loop
    while True:
        try:
            # User input
            user_input = Prompt.ask("[bold green]You[/bold green]")

            # Check for exit commands
            if user_input.strip().lower() in ["exit", "quit"]:
                console.print("\n[yellow]Exiting mnemo8...[/yellow]")
                break

            if not user_input.strip():
                continue

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
