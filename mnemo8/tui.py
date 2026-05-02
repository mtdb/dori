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


def _run_skill(skill_name: str, skill_json: dict) -> str:
    mnemo_home = os.path.expanduser("~/.mnemo8")
    script_path = os.path.join(mnemo_home, "scripts", f"{skill_name}.py")
    if not os.path.isfile(script_path):
        return f"[red]Script for skill '{skill_name}' not found[/red]"
    try:
        result = subprocess.run(
            [sys.executable, script_path, json.dumps(skill_json)],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"[red]{e.stderr.strip()}[/red]"


class MessageWidget(Static):
    def __init__(self, role: str, content: str) -> None:
        self._role = role  # "user" or "nemo"
        self._content = content
        super().__init__(classes=role)

    def render(self) -> Text:
        if self._role == "user":
            return Text.assemble(
                Text("You\n", style="bold #6fc3df"),
                Text(self._content),
            )
        return Text.assemble(
            Text("Nemo\n", style="bold #f38518"),
            Text.from_markup(self._content),
        )


class ThinkingWidget(Static):
    def render(self) -> Text:
        text = Text()
        text.append("Nemo\n", style="bold #f38518")
        text.append("⠸ thinking…", style="#555555")
        return text


class MessageList(ScrollableContainer):
    pass


class NemoInput(Input):
    async def on_key(self, event: events.Key) -> None:
        if event.key in ("up", "down"):
            direction = -1 if event.key == "up" else 1
            self.app.cycle_input_history(direction)  # type: ignore[attr-defined]
            event.prevent_default()
            event.stop()


class NemoApp(App):
    CSS_PATH = "tui.tcss"

    def __init__(self, state: RuntimeState) -> None:
        self._state = state
        self._history: list[str] = []
        self._history_idx: int = -1
        self._last_user_input: str | None = None
        self._messages: list[dict] = [
            {"role": "system", "content": _build_system_prompt(state)}
        ]
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("◆ Nemo", id="header-left"),
            Static(
                f"llama3.1:8b · {len(self._state.skills)} skills",
                id="header-right",
            ),
            id="header",
        )
        yield MessageList()
        yield Horizontal(
            Static("❯", id="prompt-label"),
            NemoInput(placeholder="Type a message…"),
            id="input-bar",
        )
        yield Static(id="footer")

    def on_mount(self) -> None:
        footer = self.query_one("#footer", Static)
        text = Text()
        text.append("[ctrl+c]", style="#6fc3df")
        text.append(" exit  ", style="#444444")
        text.append("[↑↓]", style="#f38518")
        text.append(" history  ", style="#444444")
        text.append("[/retry]", style="#6fc3df")
        text.append(" retry", style="#444444")
        footer.update(text)
        self.query_one(NemoInput).focus()

    def cycle_input_history(self, direction: int) -> None:
        self._history_idx, value = cycle_history(
            self._history, self._history_idx, direction
        )
        inp = self.query_one(NemoInput)
        inp.value = value
        inp.cursor_position = len(value)

    async def _send_message(self, user_input: str) -> None:
        msg_list = self.query_one(MessageList)
        await msg_list.mount(MessageWidget("user", user_input))
        thinking = ThinkingWidget()
        await msg_list.mount(thinking)
        msg_list.scroll_end(animate=False)

        self._messages.append({"role": "user", "content": user_input})

        response = await asyncio.to_thread(
            ollama.chat, model="llama3.1:8b", messages=self._messages
        )
        assistant_content = response["message"]["content"]
        self._messages.append({"role": "assistant", "content": assistant_content})

        await thinking.remove()
        await self._mount_nemo_response(msg_list, assistant_content)
        msg_list.scroll_end(animate=False)

    async def _mount_nemo_response(self, msg_list: MessageList, content: str) -> None:
        skill_json = _parse_skill(content)
        if skill_json:
            skill_name = skill_json["skill"]
            skill_output = _run_skill(skill_name, skill_json)
            display = f"[#6fc3df]✓ {skill_name}[/]\n{content}"
            if skill_output:
                display += f"\n{skill_output}"
        else:
            display = content
        await msg_list.mount(MessageWidget("nemo", display))


def start_tui(state: RuntimeState) -> None:
    NemoApp(state).run()
