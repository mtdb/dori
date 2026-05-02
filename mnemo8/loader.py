import os
import subprocess
from typing import List, Optional
from pathlib import Path

from mnemo8.models import Skill


def load_agents() -> Optional[str]:
    """Load AGENTS.md from the user's ~/.mnemo8 directory."""
    mnemo_home = Path.home() / ".mnemo8"
    agents_path = mnemo_home / "AGENTS.md"
    if not agents_path.is_file():
        return None

    try:
        return agents_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"Warning: Failed to decode {agents_path} as UTF-8. Skipping.")
        return None
    except Exception as e:
        print(f"Warning: Could not read {agents_path}: {e}")
        return None


def load_skills() -> List[Skill]:
    """Load all markdown files from `~/.mnemo8/skills`."""
    mnemo_home = Path.home() / ".mnemo8"
    skills_dir = mnemo_home / "skills"
    skills: List[Skill] = []

    if not skills_dir.is_dir():
        return skills

    for filepath in skills_dir.rglob("*.md"):
        if filepath.is_file():
            try:
                content = filepath.read_text(encoding="utf-8")
                skills.append(
                    Skill(
                        name=filepath.name,
                        path=str(filepath.relative_to(mnemo_home)),
                        content=content,
                    )
                )
            except UnicodeDecodeError:
                print(f"Warning: Failed to decode {filepath} as UTF-8. Skipping.")
            except Exception as e:
                print(f"Warning: Could not read {filepath}: {e}")

    return skills


def load_available_vram_mib() -> Optional[int]:
    """Return total available GPU VRAM in MiB when detectable via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    values: List[int] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            values.append(int(stripped))
        except ValueError:
            return None

    return sum(values) if values else None
