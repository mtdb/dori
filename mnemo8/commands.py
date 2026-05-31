import shutil
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from mnemo8.loader import get_runtime_home

console = Console()

REMINDERS_BACKENDS = {"dbus", "template"}
REMINDERS_SCRIPT = Path("scripts/reminders.py")
REMINDERS_SKILL = Path("skills/reminders.md")


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


def _copy_file_if_missing(src: Path, dest: Path, runtime_home: Path, repo_root: Path):
    if dest.exists():
        console.print(
            f"[yellow]Skipped[/yellow] {dest.relative_to(runtime_home)} (already exists)"
        )
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    console.print(
        f"[green]Copied[/green] {src.relative_to(repo_root)} -> {dest.relative_to(runtime_home)}"
    )


def _normalize_reminders_backend(reminders_backend: str | None) -> str | None:
    if reminders_backend is None:
        return None
    if reminders_backend not in REMINDERS_BACKENDS:
        raise ValueError(
            f"Invalid reminders backend {reminders_backend!r}. "
            f"Expected one of: {', '.join(sorted(REMINDERS_BACKENDS))}."
        )
    return reminders_backend


def _choose_reminders_backend(
    reminders_backend: str | None,
    prompt: Callable[..., str] = Prompt.ask,
) -> str:
    normalized_backend = _normalize_reminders_backend(reminders_backend)
    if normalized_backend is not None:
        return normalized_backend

    return prompt(
        "Choose reminders backend",
        choices=sorted(REMINDERS_BACKENDS),
        default="template",
    )


def _copy_reminders_preset(
    boilerplate_dir: Path,
    runtime_home: Path,
    repo_root: Path,
    reminders_backend: str | None,
):
    script_dest = runtime_home / REMINDERS_SCRIPT
    skill_dest = runtime_home / REMINDERS_SKILL
    script_exists = script_dest.exists()
    skill_exists = skill_dest.exists()

    if script_exists and skill_exists:
        console.print(
            f"[yellow]Skipped[/yellow] {REMINDERS_SCRIPT} and {REMINDERS_SKILL} (already exist)"
        )
        return

    if script_exists or skill_exists:
        backend = "template"
    else:
        backend = _choose_reminders_backend(reminders_backend)

    preset_dir = boilerplate_dir / "presets" / "reminders"
    script_src = preset_dir / f"{backend}.py"
    skill_src = preset_dir / f"{backend}.md"

    if not script_exists:
        _copy_file_if_missing(script_src, script_dest, runtime_home, repo_root)
    if not skill_exists:
        _copy_file_if_missing(skill_src, skill_dest, runtime_home, repo_root)


def init_workspace(cwd: str, reminders_backend: str | None = None):
    """Initialize ~/.dori using boilerplate files shipped with Dori."""
    reminders_backend = _normalize_reminders_backend(reminders_backend)
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
            if src.relative_to(boilerplate_dir) == REMINDERS_SCRIPT:
                continue
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
            if Path("skills") / relative == REMINDERS_SKILL:
                continue
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

    _copy_reminders_preset(
        boilerplate_dir,
        runtime_home,
        repo_root,
        reminders_backend,
    )

    console.print("\n[bold cyan]Dori ~/.dori initialized successfully![/bold cyan]")
