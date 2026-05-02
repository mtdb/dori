from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys

import ollama
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import Input, Static

from mnemo8.models import RuntimeState


def _parse_skill(content: str) -> dict | None:
    parsed = None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    if isinstance(parsed, dict) and "skill" in parsed:
        return parsed
    return None


def cycle_history(history: list[str], idx: int, direction: int) -> tuple[int, str]:
    """Return (new_idx, value) after cycling history in the given direction (-1=up, 1=down)."""
    if not history:
        return idx, ""
    if direction == -1:
        new_idx = len(history) - 1 if idx == -1 else max(0, idx - 1)
    else:
        if idx == -1:
            return -1, ""
        new_idx = idx + 1
        if new_idx >= len(history):
            new_idx = -1
    value = "" if new_idx == -1 else history[new_idx]
    return new_idx, value


def _build_system_prompt(state: RuntimeState) -> str:
    prompt = "You are mnemo8, a helpful personal assistant CLI running on the user's terminal.\n"
    if state.agents_content:
        prompt += f"\nHere is information about your agent configuration:\n{state.agents_content}\n"
    if state.skills:
        prompt += "\nHere are your available skills that you should be aware of:\n"
        prompt += (
            "IMPORTANT: If the user asks you to perform an action that matches an available skill, "
            "you MUST output a JSON code block with the exact arguments required by the skill.\n"
        )
        for skill in state.skills:
            prompt += f"\n--- Skill: {skill.name} ---\n{skill.content}\n"
    return prompt
