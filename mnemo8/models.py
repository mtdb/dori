from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Skill:
    name: str
    path: str
    content: str


@dataclass
class RuntimeState:
    cwd: str
    agents_content: Optional[str] = None
    skills: List[Skill] = field(default_factory=list)
    chat_history: List[str] = field(default_factory=list)
    model: str = "llama3.1:8b"
