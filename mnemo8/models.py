from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Skill:
    name: str
    path: str
    content: str
    children: list[Skill] = field(default_factory=list)

    @property
    def is_router(self) -> bool:
        return len(self.children) > 0


@dataclass
class RuntimeState:
    cwd: str
    agents_content: str | None = None
    skills: list[Skill] = field(default_factory=list)
    chat_history: list[str] = field(default_factory=list)
    model: str = "llama3.1:8b"
    available_vram_mib: int | None = None
    total_vram_mib: int | None = None
    debug: bool = False
    skill_confidence_threshold: float = 0.8
    initial_prompt: str | None = None
