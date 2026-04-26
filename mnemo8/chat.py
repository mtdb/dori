import sys
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown

import ollama

from mnemo8.models import RuntimeState

console = Console()

def build_system_prompt(state: RuntimeState) -> str:
    prompt = "You are Mnemo8, a helpful personal assistant CLI running on the user's terminal.\n"
    if state.agents_content:
        prompt += f"\nHere is information about available agents that might be relevant:\n{state.agents_content}\n"
    if state.skills:
        prompt += "\nHere are your available skills that you should be aware of:\n"
        for skill in state.skills:
            prompt += f"\n--- Skill: {skill.name} ---\n{skill.content}\n"
    return prompt

def start_chat(state: RuntimeState):
    """Start the REPL chat loop."""
    
    # Startup Summary
    console.print(f"\n[bold cyan]Mnemo8 Personal Assistant[/bold cyan]")
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
                console.print("\n[yellow]Exiting Mnemo8...[/yellow]")
                break
                
            if not user_input.strip():
                continue
                
            messages.append({"role": "user", "content": user_input})
            
            with console.status("[bold cyan]Thinking...[/bold cyan]"):
                response = ollama.chat(
                    model='llama3.1:8b',
                    messages=messages
                )
            
            assistant_content = response['message']['content']
            messages.append({"role": "assistant", "content": assistant_content})
            
            console.print("\n[bold cyan]Mnemo8[/bold cyan] >")
            console.print(Markdown(assistant_content))
            console.print()
            
        except (KeyboardInterrupt, EOFError):
            console.print("\n\n[yellow]Exiting Mnemo8...[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]An error occurred: {e}[/red]")
