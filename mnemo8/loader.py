import os
from typing import List, Optional
from pathlib import Path

from mnemo8.models import Skill


def load_agents(cwd: str) -> Optional[str]:
    """Load AGENTS.md from the current working directory."""
    agents_path = Path(cwd) / "AGENTS.md"
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


def load_skills(cwd: str) -> List[Skill]:
    """Load all markdown files from the skills/ directory."""
    skills_dir = Path(cwd) / "skills"
    skills = []
    
    if not skills_dir.is_dir():
        return skills

    for filepath in skills_dir.rglob("*.md"):
        if filepath.is_file():
            try:
                content = filepath.read_text(encoding="utf-8")
                skills.append(
                    Skill(
                        name=filepath.name,
                        path=str(filepath.relative_to(cwd)),
                        content=content,
                    )
                )
            except UnicodeDecodeError:
                print(f"Warning: Failed to decode {filepath} as UTF-8. Skipping.")
            except Exception as e:
                print(f"Warning: Could not read {filepath}: {e}")
                
    return skills
