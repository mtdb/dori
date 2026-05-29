import shutil
from pathlib import Path

from rich.console import Console

from mnemo8.loader import get_runtime_home

console = Console()


def _resolve_boilerplate_dir(cwd: str) -> tuple[Path, Path, bool]:
    """Find boilerplate/ from cwd first, then fall back to the package repo root."""
    requested_root = Path(cwd).expanduser().resolve()
    requested_boilerplate = requested_root / "boilerplate"
    if requested_boilerplate.is_dir():
        return requested_root, requested_boilerplate, False

    package_repo_root = Path(__file__).resolve().parent.parent
    package_boilerplate = package_repo_root / "boilerplate"
    if package_boilerplate.is_dir():
        return package_repo_root, package_boilerplate, True

    return requested_root, requested_boilerplate, False


def init_workspace(cwd: str):
    """Initialize ~/.dori using boilerplate files shipped with Dori."""
    repo_root, boilerplate_dir, used_fallback = _resolve_boilerplate_dir(cwd)
    runtime_home = get_runtime_home()

    if used_fallback:
        console.print(
            f"[yellow]Using bundled boilerplate at {boilerplate_dir}[/yellow]"
        )

    # Ensure ~/.dori exists
    if not runtime_home.exists():
        runtime_home.mkdir(parents=True)
        console.print(f"[green]Created[/green] {runtime_home}")
    else:
        console.print(f"[yellow]Using existing[/yellow] {runtime_home}")

    # Copy AGENTS.md
    agents_src = boilerplate_dir / "AGENTS.md"
    agents_dest = runtime_home / "AGENTS.md"
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
    scripts_dest = runtime_home / "scripts"
    if scripts_src.is_dir():
        scripts_dest.mkdir(exist_ok=True)
        for src in scripts_src.glob("*.py"):
            dest = scripts_dest / src.name
            if dest.exists():
                console.print(
                    f"[yellow]Skipped[/yellow] {dest.relative_to(runtime_home)} (already exists)"
                )
            else:
                shutil.copy2(src, dest)
                console.print(
                    f"[green]Copied[/green] {src.relative_to(repo_root)} -> {dest.relative_to(runtime_home)}"
                )
    else:
        console.print(
            f"[yellow]No boilerplate scripts/ directory found at {scripts_src}[/yellow]"
        )

    # Copy skills/
    skills_src = boilerplate_dir / "skills"
    skills_dest = runtime_home / "skills"
    if skills_src.is_dir():
        for src in skills_src.rglob("*.md"):
            relative = src.relative_to(skills_src)
            dest = skills_dest / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                console.print(
                    f"[yellow]Skipped[/yellow] {dest.relative_to(runtime_home)} (already exists)"
                )
            else:
                shutil.copy2(src, dest)
                console.print(
                    f"[green]Copied[/green] {src.relative_to(repo_root)} -> {dest.relative_to(runtime_home)}"
                )
    else:
        console.print(
            f"[yellow]No boilerplate skills/ directory found at {skills_src}[/yellow]"
        )

    console.print("\n[bold cyan]Dori ~/.dori initialized successfully![/bold cyan]")
