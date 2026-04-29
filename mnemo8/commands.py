import shutil
from pathlib import Path
from rich.console import Console

console = Console()


def init_workspace(cwd: str):
    """Initializes the user's ~/.mnemo8 directory from the repository `boilerplate/`.

    `cwd` should be the repository root (where `boilerplate/` lives).
    """
    repo_root = Path(cwd)
    boilerplate_dir = repo_root / "boilerplate"
    mnemo_home = Path.home() / ".mnemo8"

    # Ensure ~/.mnemo8 exists
    if not mnemo_home.exists():
        mnemo_home.mkdir(parents=True)
        console.print(f"[green]Created[/green] {mnemo_home}")
    else:
        console.print(f"[yellow]Using existing[/yellow] {mnemo_home}")

    # Copy AGENTS.md
    agents_src = boilerplate_dir / "AGENTS.md"
    agents_dest = mnemo_home / "AGENTS.md"
    if agents_dest.exists():
        console.print(f"[yellow]Skipped[/yellow] {agents_dest.name} (already exists)")
    else:
        if agents_src.is_file():
            shutil.copy2(agents_src, agents_dest)
            console.print(
                f"[green]Copied[/green] {agents_src.relative_to(repo_root)} -> {agents_dest}"
            )
        else:
            console.print(f"[red]Boilerplate AGENTS.md not found at {agents_src}[/red]")

    # Copy scripts/
    scripts_src = boilerplate_dir / "scripts"
    scripts_dest = mnemo_home / "scripts"
    if scripts_src.is_dir():
        scripts_dest.mkdir(exist_ok=True)
        for src in scripts_src.glob("*.py"):
            dest = scripts_dest / src.name
            if dest.exists():
                console.print(
                    f"[yellow]Skipped[/yellow] {dest.relative_to(mnemo_home)} (already exists)"
                )
            else:
                shutil.copy2(src, dest)
                console.print(
                    f"[green]Copied[/green] {src.relative_to(repo_root)} -> {dest.relative_to(mnemo_home)}"
                )
    else:
        console.print(
            f"[yellow]No boilerplate scripts/ directory found at {scripts_src}[/yellow]"
        )

    # Copy skills/
    skills_src = boilerplate_dir / "skills"
    skills_dest = mnemo_home / "skills"
    if skills_src.is_dir():
        skills_dest.mkdir(exist_ok=True)
        for src in skills_src.rglob("*.md"):
            dest = skills_dest / src.name
            if dest.exists():
                console.print(
                    f"[yellow]Skipped[/yellow] {dest.relative_to(mnemo_home)} (already exists)"
                )
            else:
                shutil.copy2(src, dest)
                console.print(
                    f"[green]Copied[/green] {src.relative_to(repo_root)} -> {dest.relative_to(mnemo_home)}"
                )
    else:
        console.print(
            f"[yellow]No boilerplate skills/ directory found at {skills_src}[/yellow]"
        )

    console.print("\n[bold cyan]mnemo8 ~/.mnemo8 initialized successfully![/bold cyan]")
