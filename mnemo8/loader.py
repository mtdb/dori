import subprocess
from pathlib import Path

from mnemo8.models import Skill

RUNTIME_HOME_DIRNAME = ".dori"


def get_runtime_home() -> Path:
    """Return Dori's public runtime home directory."""
    return Path.home() / RUNTIME_HOME_DIRNAME


def load_agents() -> str | None:
    """Load DORI.md from the user's ~/.dori directory."""
    runtime_home = get_runtime_home()
    persona_path = runtime_home / "DORI.md"
    if not persona_path.is_file():
        return None

    try:
        return persona_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"Warning: Failed to decode {persona_path} as UTF-8. Skipping.")
        return None
    except Exception as e:
        print(f"Warning: Could not read {persona_path}: {e}")
        return None


def load_skills() -> list[Skill]:
    """Load skills from `~/.dori/skills`, building a tree from subdirectories."""
    runtime_home = get_runtime_home()
    skills_dir = runtime_home / "skills"
    if not skills_dir.is_dir():
        return []
    return _load_node(skills_dir, skills_dir)


def _load_node(directory: Path, root: Path) -> list[Skill]:
    """Recursively load skills from a directory.

    Files (*.md, excluding _index.md) become leaf skills.
    Subdirectories become router skills whose content is taken from _index.md
    if present, or a minimal auto-generated description otherwise.
    """
    skills: list[Skill] = []
    try:
        entries = sorted(directory.iterdir())
    except PermissionError as e:
        print(f"Warning: Cannot read directory {directory}: {e}")
        return skills

    for item in entries:
        if item.is_file() and item.suffix == ".md" and item.stem != "_index":
            try:
                content = item.read_text(encoding="utf-8")
                skills.append(
                    Skill(
                        name=item.stem,
                        path=str(item.relative_to(root)),
                        content=content,
                    )
                )
            except UnicodeDecodeError:
                print(f"Warning: Failed to decode {item} as UTF-8. Skipping.")
            except Exception as e:
                print(f"Warning: Could not read {item}: {e}")
        elif item.is_dir():
            try:
                index_path = item / "_index.md"
                if index_path.is_file():
                    content = index_path.read_text(encoding="utf-8")
                else:
                    content = (
                        f"# {item.name}\n**Intent**: Tasks related to {item.name}.\n"
                    )
                children = _load_node(item, root)
                if children:
                    skills.append(
                        Skill(
                            name=item.name,
                            path=str(item.relative_to(root)),
                            content=content,
                            children=children,
                        )
                    )
            except UnicodeDecodeError:
                print(f"Warning: Failed to decode {index_path} as UTF-8. Skipping.")
            except Exception as e:
                print(f"Warning: Could not load router skill {item}: {e}")

    return skills


def load_available_vram() -> tuple[int | None, int | None]:
    """Return (free_mib, total_mib) from nvidia-smi. Returns (None, None) if unavailable."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return (None, None)

    free_values: list[int] = []
    total_values: list[int] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(",")
        if len(parts) != 2:
            return (None, None)
        try:
            free_values.append(int(parts[0].strip()))
            total_values.append(int(parts[1].strip()))
        except ValueError:
            return (None, None)

    free_total = sum(free_values) if free_values else None
    total_total = sum(total_values) if total_values else None
    return (free_total, total_total)
