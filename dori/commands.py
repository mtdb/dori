import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from dori.loader import get_runtime_home

console = Console()

REMINDERS_BACKENDS = {"dbus", "template"}
REMINDERS_SCRIPT = Path("scripts/reminders.py")
REMINDERS_SKILL = Path("skills/reminders.md")
SEARCH_BACKENDS = {"ddgs", "tavily"}
SEARCH_SCRIPT = Path("scripts/web.py")
SEARCH_SKILL = Path("skills/web.md")
LEGACY_SEARCH_PATHS = {
    Path("skills/search/_index.md"),
    Path("skills/search/web.md"),
    Path("skills/search/news.md"),
    Path("scripts/news.py"),
}
MANIFEST_PATH = Path(".manifest.json")
PERSONA_FILENAME = "DORI.md"
LEGACY_PERSONA_FILENAME = "AGENTS.md"


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


def _copy_file_if_missing(
    src: Path, dest: Path, runtime_home: Path, repo_root: Path
) -> bool:
    if dest.exists():
        console.print(
            f"[yellow]Skipped[/yellow] {dest.relative_to(runtime_home)} (already exists)"
        )
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    console.print(
        f"[green]Copied[/green] {src.relative_to(repo_root)} -> {dest.relative_to(runtime_home)}"
    )
    return True


def _compute_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324


def _load_manifest(runtime_home: Path) -> dict[str, str]:
    manifest_path = runtime_home / MANIFEST_PATH
    if not manifest_path.is_file():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _write_manifest(runtime_home: Path, manifest: dict[str, str]) -> None:
    manifest_path = runtime_home / MANIFEST_PATH
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _relative_runtime_path(path: Path, runtime_home: Path) -> str:
    return path.relative_to(runtime_home).as_posix()


def migrate_legacy_persona_file(
    runtime_home: Path, manifest: dict[str, str] | None = None
) -> bool:
    """Copy legacy AGENTS.md content into DORI.md when upgrading older installs."""
    persona_path = runtime_home / PERSONA_FILENAME
    legacy_path = runtime_home / LEGACY_PERSONA_FILENAME

    if persona_path.is_file():
        if manifest is not None and LEGACY_PERSONA_FILENAME in manifest:
            manifest[PERSONA_FILENAME] = manifest.pop(LEGACY_PERSONA_FILENAME)
        return False

    if not legacy_path.is_file():
        return False

    persona_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy_path, persona_path)
    console.print(f"[green]Migrated[/green] {legacy_path.name} -> {persona_path.name}")

    if manifest is not None:
        if LEGACY_PERSONA_FILENAME in manifest:
            manifest[PERSONA_FILENAME] = manifest.pop(LEGACY_PERSONA_FILENAME)
        else:
            manifest[PERSONA_FILENAME] = _compute_md5(persona_path)

    return True


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


def _normalize_search_backend(search_backend: str | None) -> str | None:
    if search_backend is None:
        return None
    if search_backend not in SEARCH_BACKENDS:
        raise ValueError(
            f"Invalid search backend {search_backend!r}. "
            f"Expected one of: {', '.join(sorted(SEARCH_BACKENDS))}."
        )
    return search_backend


def _choose_search_backend(
    search_backend: str | None,
    prompt: Callable[..., str] = Prompt.ask,
) -> str:
    normalized_backend = _normalize_search_backend(search_backend)
    if normalized_backend is not None:
        return normalized_backend

    return prompt(
        "Choose search backend",
        choices=sorted(SEARCH_BACKENDS),
        default="ddgs",
    )


def _copy_reminders_preset(
    boilerplate_dir: Path,
    runtime_home: Path,
    repo_root: Path,
    reminders_backend: str | None,
) -> set[str]:
    copied_paths: set[str] = set()
    script_dest = runtime_home / REMINDERS_SCRIPT
    skill_dest = runtime_home / REMINDERS_SKILL
    script_exists = script_dest.exists()
    skill_exists = skill_dest.exists()

    if script_exists and skill_exists:
        console.print(
            f"[yellow]Skipped[/yellow] {REMINDERS_SCRIPT} and {REMINDERS_SKILL} (already exist)"
        )
        return copied_paths

    if script_exists or skill_exists:
        backend = "template"
    else:
        backend = _choose_reminders_backend(reminders_backend)

    preset_dir = boilerplate_dir / "presets" / "reminders"
    script_src = preset_dir / f"{backend}.py"
    skill_src = preset_dir / f"{backend}.md"

    if not script_exists:
        if _copy_file_if_missing(script_src, script_dest, runtime_home, repo_root):
            copied_paths.add(_relative_runtime_path(script_dest, runtime_home))
    if not skill_exists:
        if _copy_file_if_missing(skill_src, skill_dest, runtime_home, repo_root):
            copied_paths.add(_relative_runtime_path(skill_dest, runtime_home))
    return copied_paths


def _copy_search_preset(
    boilerplate_dir: Path,
    runtime_home: Path,
    repo_root: Path,
    search_backend: str | None,
) -> set[str]:
    copied_paths: set[str] = set()
    script_dest = runtime_home / SEARCH_SCRIPT
    skill_dest = runtime_home / SEARCH_SKILL
    script_exists = script_dest.exists()
    skill_exists = skill_dest.exists()

    if script_exists and skill_exists:
        console.print(
            f"[yellow]Skipped[/yellow] {SEARCH_SCRIPT} and {SEARCH_SKILL} (already exist)"
        )
        return copied_paths

    if script_exists or skill_exists:
        backend = "ddgs"
    else:
        backend = _choose_search_backend(search_backend)

    preset_dir = boilerplate_dir / "presets" / "search"
    script_src = preset_dir / f"{backend}.py"
    skill_src = preset_dir / f"{backend}.md"

    if not script_exists:
        if _copy_file_if_missing(script_src, script_dest, runtime_home, repo_root):
            copied_paths.add(_relative_runtime_path(script_dest, runtime_home))
    if not skill_exists:
        if _copy_file_if_missing(skill_src, skill_dest, runtime_home, repo_root):
            copied_paths.add(_relative_runtime_path(skill_dest, runtime_home))
    return copied_paths


def _detect_existing_reminders_backend(
    boilerplate_dir: Path, runtime_home: Path
) -> str | None:
    preset_dir = boilerplate_dir / "presets" / "reminders"
    script_dest = runtime_home / REMINDERS_SCRIPT
    skill_dest = runtime_home / REMINDERS_SKILL

    for backend in sorted(REMINDERS_BACKENDS):
        script_src = preset_dir / f"{backend}.py"
        skill_src = preset_dir / f"{backend}.md"
        if script_dest.is_file() and script_src.is_file():
            if _compute_md5(script_dest) == _compute_md5(script_src):
                return backend
        if skill_dest.is_file() and skill_src.is_file():
            if _compute_md5(skill_dest) == _compute_md5(skill_src):
                return backend
    return None


def _read_search_backend_marker(script_path: Path) -> str | None:
    if not script_path.is_file():
        return None

    for line in script_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("SEARCH_BACKEND = "):
            continue
        marker = line.partition("=")[2].strip().strip("\"'")
        if marker in SEARCH_BACKENDS:
            return marker
    return None


def _detect_existing_search_backend(
    boilerplate_dir: Path, runtime_home: Path, manifest: dict[str, str]
) -> str | None:
    preset_dir = boilerplate_dir / "presets" / "search"
    script_dest = runtime_home / SEARCH_SCRIPT
    skill_dest = runtime_home / SEARCH_SKILL

    for backend in sorted(SEARCH_BACKENDS):
        script_src = preset_dir / f"{backend}.py"
        skill_src = preset_dir / f"{backend}.md"
        if (
            script_dest.is_file()
            and skill_dest.is_file()
            and script_src.is_file()
            and skill_src.is_file()
            and _compute_md5(script_dest) == _compute_md5(script_src)
            and _compute_md5(skill_dest) == _compute_md5(skill_src)
        ):
            return backend

    relative = SEARCH_SCRIPT.as_posix()
    recorded_md5 = manifest.get(relative)
    if (
        recorded_md5 is not None
        and script_dest.is_file()
        and _compute_md5(script_dest) == recorded_md5
    ):
        return _read_search_backend_marker(script_dest)
    return None


def _search_pair_is_managed_and_unmodified(
    runtime_home: Path, manifest: dict[str, str]
) -> bool:
    for relative_path in (SEARCH_SCRIPT, SEARCH_SKILL):
        relative = relative_path.as_posix()
        destination = runtime_home / relative_path
        recorded_md5 = manifest.get(relative)
        if (
            not destination.is_file()
            or recorded_md5 is None
            or _compute_md5(destination) != recorded_md5
        ):
            return False
    return True


def _iter_managed_files(
    boilerplate_dir: Path,
    runtime_home: Path,
    reminders_backend: str | None = None,
    search_backend: str | None = None,
    *,
    include_search: bool = True,
    manifest: dict[str, str] | None = None,
) -> list[tuple[Path, Path]]:
    managed_files: list[tuple[Path, Path]] = []

    persona_src = boilerplate_dir / PERSONA_FILENAME
    if persona_src.is_file():
        managed_files.append((persona_src, runtime_home / PERSONA_FILENAME))

    assets_src = boilerplate_dir / "assets"
    if assets_src.is_dir():
        for src in sorted(path for path in assets_src.rglob("*") if path.is_file()):
            managed_files.append(
                (src, runtime_home / "assets" / src.relative_to(assets_src))
            )

    scripts_src = boilerplate_dir / "scripts"
    if scripts_src.is_dir():
        for src in sorted(scripts_src.glob("*.py")):
            if src.relative_to(boilerplate_dir) in {REMINDERS_SCRIPT, SEARCH_SCRIPT}:
                continue
            managed_files.append((src, runtime_home / "scripts" / src.name))

    skills_src = boilerplate_dir / "skills"
    if skills_src.is_dir():
        for src in sorted(skills_src.rglob("*.md")):
            relative = src.relative_to(skills_src)
            if Path("skills") / relative in {REMINDERS_SKILL, SEARCH_SKILL}:
                continue
            managed_files.append((src, runtime_home / "skills" / relative))

    resolved_backend = reminders_backend
    if resolved_backend is None:
        resolved_backend = _detect_existing_reminders_backend(
            boilerplate_dir, runtime_home
        )
    if resolved_backend is None:
        resolved_backend = "template"
    preset_dir = boilerplate_dir / "presets" / "reminders"
    managed_files.append(
        (preset_dir / f"{resolved_backend}.py", runtime_home / REMINDERS_SCRIPT)
    )
    managed_files.append(
        (preset_dir / f"{resolved_backend}.md", runtime_home / REMINDERS_SKILL)
    )
    if include_search:
        resolved_search_backend = search_backend
        if resolved_search_backend is None:
            resolved_search_backend = _detect_existing_search_backend(
                boilerplate_dir, runtime_home, manifest or {}
            )
        if resolved_search_backend is None:
            resolved_search_backend = "ddgs"
        search_preset_dir = boilerplate_dir / "presets" / "search"
        managed_files.append(
            (
                search_preset_dir / f"{resolved_search_backend}.py",
                runtime_home / SEARCH_SCRIPT,
            )
        )
        managed_files.append(
            (
                search_preset_dir / f"{resolved_search_backend}.md",
                runtime_home / SEARCH_SKILL,
            )
        )
    return managed_files


def _remove_managed_legacy_search_files(
    runtime_home: Path, manifest: dict[str, str]
) -> None:
    legacy_install = any(path.as_posix() in manifest for path in LEGACY_SEARCH_PATHS)
    paths = set(LEGACY_SEARCH_PATHS)
    if legacy_install and SEARCH_SKILL.as_posix() not in manifest:
        paths.add(SEARCH_SCRIPT)

    for relative_path in sorted(paths):
        relative = relative_path.as_posix()
        destination = runtime_home / relative_path
        if not destination.exists():
            manifest.pop(relative, None)
            continue

        recorded_md5 = manifest.get(relative)
        if recorded_md5 is None or _compute_md5(destination) != recorded_md5:
            console.print(
                f"[yellow]Skipped[/yellow] {relative} "
                "(not removed because it has local modifications)"
            )
            continue

        destination.unlink()
        manifest.pop(relative, None)
        console.print(f"[green]Removed[/green] {relative}")

    search_dir = runtime_home / "skills" / "search"
    if search_dir.is_dir() and not any(search_dir.iterdir()):
        search_dir.rmdir()


def init_workspace(
    cwd: str,
    reminders_backend: str | None = None,
    search_backend: str | None = None,
):
    """Initialize ~/.dori using boilerplate files shipped with Dori."""
    reminders_backend = _normalize_reminders_backend(reminders_backend)
    search_backend = _normalize_search_backend(search_backend)
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

    manifest = _load_manifest(runtime_home)
    managed_paths = set(manifest)

    # Copy DORI.md
    persona_src = boilerplate_dir / PERSONA_FILENAME
    persona_dest = runtime_home / PERSONA_FILENAME
    if persona_dest.exists():
        console.print(f"[yellow]Skipped[/yellow] {persona_dest.name} (already exists)")
    else:
        if persona_src.is_file():
            shutil.copy2(persona_src, persona_dest)
            console.print(
                f"[green]Copied[/green] {persona_src.relative_to(repo_root)} -> {persona_dest}"
            )
            managed_paths.add(_relative_runtime_path(persona_dest, runtime_home))
        else:
            console.print(f"[red]Boilerplate DORI.md not found at {persona_src}[/red]")

    # Copy assets/
    assets_src = boilerplate_dir / "assets"
    assets_dest = runtime_home / "assets"
    if assets_src.is_dir():
        for src in assets_src.rglob("*"):
            if not src.is_file():
                continue
            relative = src.relative_to(assets_src)
            dest = assets_dest / relative
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
                managed_paths.add(_relative_runtime_path(dest, runtime_home))
    else:
        console.print(
            f"[yellow]No boilerplate assets/ directory found at {assets_src}[/yellow]"
        )

    # Copy scripts/
    scripts_src = boilerplate_dir / "scripts"
    scripts_dest = runtime_home / "scripts"
    if scripts_src.is_dir():
        scripts_dest.mkdir(exist_ok=True)
        for src in scripts_src.glob("*.py"):
            if src.relative_to(boilerplate_dir) in {REMINDERS_SCRIPT, SEARCH_SCRIPT}:
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
                managed_paths.add(_relative_runtime_path(dest, runtime_home))
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
            if Path("skills") / relative in {REMINDERS_SKILL, SEARCH_SKILL}:
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
                managed_paths.add(_relative_runtime_path(dest, runtime_home))
    else:
        console.print(
            f"[yellow]No boilerplate skills/ directory found at {skills_src}[/yellow]"
        )

    managed_paths.update(
        _copy_reminders_preset(
            boilerplate_dir,
            runtime_home,
            repo_root,
            reminders_backend,
        )
    )
    managed_paths.update(
        _copy_search_preset(
            boilerplate_dir,
            runtime_home,
            repo_root,
            search_backend,
        )
    )

    for relative_path in sorted(managed_paths):
        dest = runtime_home / relative_path
        if dest.is_file():
            manifest[relative_path] = _compute_md5(dest)

    _write_manifest(runtime_home, manifest)

    console.print("\n[bold cyan]Dori ~/.dori initialized successfully![/bold cyan]")


def update_workspace(
    cwd: str,
    reminders_backend: str | None = None,
    search_backend: str | None = None,
) -> None:
    """Update managed files in ~/.dori without overwriting user-modified files."""
    reminders_backend = _normalize_reminders_backend(reminders_backend)
    search_backend = _normalize_search_backend(search_backend)
    _, boilerplate_dir, used_fallback = _resolve_boilerplate_dir(cwd)
    runtime_home = get_runtime_home()

    if not runtime_home.is_dir():
        raise FileNotFoundError("~/.dori not found. Please run 'dori init' first.")

    if used_fallback:
        console.print(
            f"[yellow]Using bundled boilerplate at {boilerplate_dir}[/yellow]"
        )

    manifest = _load_manifest(runtime_home)
    migrate_legacy_persona_file(runtime_home, manifest)
    detected_search_backend = _detect_existing_search_backend(
        boilerplate_dir, runtime_home, manifest
    )
    resolved_search_backend = search_backend or detected_search_backend or "ddgs"
    search_pair_exists = any(
        (runtime_home / path).exists() for path in (SEARCH_SCRIPT, SEARCH_SKILL)
    )
    skip_search_update = False
    if (
        search_backend is not None
        and detected_search_backend is not None
        and search_pair_exists
        and not _search_pair_is_managed_and_unmodified(runtime_home, manifest)
    ):
        console.print(
            "[yellow]Skipped[/yellow] search backend not switched "
            "(web skill or script has local modifications)"
        )
        skip_search_update = True

    _remove_managed_legacy_search_files(runtime_home, manifest)

    for src, dest in _iter_managed_files(
        boilerplate_dir,
        runtime_home,
        reminders_backend,
        resolved_search_backend,
        include_search=not skip_search_update,
        manifest=manifest,
    ):
        relative = _relative_runtime_path(dest, runtime_home)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if not dest.exists():
            shutil.copy2(src, dest)
            manifest[relative] = _compute_md5(dest)
            console.print(f"[green]Copied[/green] {relative}")
            continue

        recorded_md5 = manifest.get(relative)
        current_md5 = _compute_md5(dest)
        if recorded_md5 is None or recorded_md5 != current_md5:
            console.print(
                f"[yellow]Skipped[/yellow] {relative} "
                "(not updated because it has local modifications)"
            )
            continue

        shutil.copy2(src, dest)
        manifest[relative] = _compute_md5(dest)
        console.print(f"[green]Updated[/green] {relative}")

    _write_manifest(runtime_home, manifest)
