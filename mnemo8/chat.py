import sys
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from mnemo8.models import RuntimeState

console = Console()

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

    # REPL Loop
    while True:
        try:
            # User input
            user_input = Prompt.ask("[bold green]You[/bold green]")
            
            # Check for exit commands
            if user_input.strip().lower() in ["exit", "quit"]:
                console.print("\n[yellow]Exiting Mnemo8...[/yellow]")
                break
                
            # Dummy response
            console.print("[bold cyan]Mnemo8[/bold cyan] > This is a dummy MVP response. Assistant runtime loaded successfully.\n")
            
        except (KeyboardInterrupt, EOFError):
            console.print("\n\n[yellow]Exiting Mnemo8...[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]An error occurred: {e}[/red]")
