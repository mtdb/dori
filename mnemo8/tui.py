import asyncio
import json
import math
import os
import re
import subprocess
import sys
import time
from contextlib import suppress

import ollama
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Input, Static

from mnemo8.loader import load_available_vram
from mnemo8.models import RuntimeState

COLOR_USER = "#6fc3df"
COLOR_NEMO = "#f38518"
COLOR_THINKING = "#555555"
AGENT_DISPLAY_NAME = "Dori"
VRAM_POLL_BURST_WINDOW_SECONDS = 13.0
VRAM_POLL_TAU_SECONDS = 60.0
VRAM_POLL_BUCKETS = (1, 5, 10, 15, 20, 30)
VRAM_UPDATE_THRESHOLD_MIB = 64


def _is_standalone_skill_payload(content: str) -> bool:
    stripped = content.strip()
    if not stripped:
        return False
    if stripped.startswith("{") and stripped.endswith("}"):
        return True
    return bool(re.fullmatch(r"```(?:json)?\s*\{.*?\}\s*```", stripped, re.DOTALL))


def _extract_skill_payload(content: str) -> dict | None:
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

    if not isinstance(parsed, dict):
        return None

    skill_name = parsed.get("skill")
    confidence = parsed.get("confidence")
    if not isinstance(skill_name, str) or not skill_name.strip():
        return None
    if confidence is None:
        if not _is_standalone_skill_payload(content):
            return None
        confidence_value = 1.0
    else:
        if isinstance(confidence, bool) or not isinstance(
            confidence, (int, float, str)
        ):
            return None
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            return None
    if not 0.0 <= confidence_value <= 1.0:
        return None

    payload = dict(parsed)
    payload["skill"] = skill_name.strip()
    payload["confidence"] = confidence_value
    return payload


def _format_vram_bar(free_mib: int | None, total_mib: int | None) -> str:
    if free_mib is None or total_mib is None or total_mib == 0:
        return "VRAM n/a"

    used_mib = total_mib - free_mib
    used_percent = used_mib / total_mib

    bar_length = 10
    filled = int(used_percent * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)

    free_gib = free_mib / 1024
    if free_gib < 1:
        return f"[{bar}] {free_mib} MiB free"
    return f"[{bar}] {free_gib:.1f} GiB free"


def _count_leaf_skills(skills: list) -> int:
    """Count all leaf (executable) skills in the tree."""
    total = 0
    for s in skills:
        if s.is_router:
            total += _count_leaf_skills(s.children)
        else:
            total += 1
    return total


def _build_routing_messages(user_message: str, candidates: list) -> list[dict]:
    """Build a minimal ephemeral prompt for one routing step."""
    options = "\n".join(
        f'- "{s.name}": {s.content.splitlines()[0].lstrip("#").strip()}'
        for s in candidates
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a router. Pick the single best option for the user's request.\n"
                "Respond with a JSON object with keys 'skill' (one of the option names) "
                "and 'confidence' (float 0.0–1.0). No prose, no markdown.\n\n"
                f"Options:\n{options}"
            ),
        },
        {"role": "user", "content": user_message},
    ]


def _build_header_status(state: RuntimeState) -> str:
    leaf_count = _count_leaf_skills(state.skills)
    return (
        f"{state.model}"
        f" · {leaf_count} skills"
        f" · {_format_vram_bar(state.available_vram_mib, state.total_vram_mib)}"
    )


def compute_vram_poll_interval(idle_seconds: float) -> int:
    if idle_seconds <= VRAM_POLL_BURST_WINDOW_SECONDS:
        return VRAM_POLL_BUCKETS[0]

    ramp = 5.0 + 25.0 * (
        1.0
        - math.exp(
            -(idle_seconds - VRAM_POLL_BURST_WINDOW_SECONDS) / VRAM_POLL_TAU_SECONDS
        )
    )
    return min(VRAM_POLL_BUCKETS[1:], key=lambda bucket: (abs(bucket - ramp), bucket))


def _parse_skill(content: str, min_confidence: float = 0.0) -> dict | None:
    payload = _extract_skill_payload(content)
    if payload and payload["confidence"] >= min_confidence:
        return payload
    return None


def _strip_skill_payload(content: str) -> str:
    payload = _extract_skill_payload(content)
    if payload is None:
        return content

    stripped = content.strip()
    try:
        if json.loads(stripped) == payload:
            return ""
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", content, flags=re.DOTALL)
    return cleaned.strip()


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
            "IMPORTANT: When a skill clearly matches the user's request, respond with a single JSON object only. "
            "Do not add markdown, explanation, or extra prose. The JSON must include the exact skill arguments "
            "plus a numeric 'confidence' field between 0.0 and 1.0. Only emit skill JSON when confidence is at "
            f"least {state.skill_confidence_threshold:.2f}; otherwise answer normally or ask a short clarifying question.\n"
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


def _write_clipboard(text: str) -> None:
    # OSC 52 (Textual's built-in) is unreliable on most Linux terminals;
    # prefer native clipboard tools when available.
    if os.environ.get("WAYLAND_DISPLAY"):
        cmd = ["wl-copy"]
    elif os.environ.get("DISPLAY"):
        cmd = ["xclip", "-selection", "clipboard"]
    else:
        cmd = None
    if cmd:
        try:
            subprocess.run(cmd, input=text, text=True, check=True)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    # fallback: OSC 52 terminal sequence
    import base64

    encoded = base64.b64encode(text.encode()).decode()
    sys.stdout.write(f"\x1b]52;c;{encoded}\a")
    sys.stdout.flush()


class MessageWidget(Static):
    def __init__(self, role: str, content: str) -> None:
        self._role = role  # "user" or "nemo"
        self._content = content
        super().__init__(classes=role)

    def render(self) -> Text:
        if self._role == "user":
            return Text.assemble(
                Text("You\n", style=f"bold {COLOR_USER}"),
                Text(self._content),
            )
        return Text.assemble(
            Text(f"{AGENT_DISPLAY_NAME}\n", style=f"bold {COLOR_NEMO}"),
            Text.from_markup(self._content),
        )


class ThinkingWidget(Static):
    FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self) -> None:
        self._frame_index = 0
        super().__init__()

    def on_mount(self) -> None:
        self.set_interval(0.12, self.advance_frame)

    def advance_frame(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(self.FRAMES)
        self.refresh()

    def render(self) -> Text:
        text = Text()
        text.append(f"{AGENT_DISPLAY_NAME}\n", style=f"bold {COLOR_NEMO}")
        text.append(
            f"{self.FRAMES[self._frame_index]} thinking…",
            style=COLOR_THINKING,
        )
        return text


class MessageList(ScrollableContainer):
    pass


def _build_chat_transcript(widgets: list[Widget]) -> str:
    lines: list[str] = []
    for widget in widgets:
        if not isinstance(widget, MessageWidget):
            continue
        speaker = "You" if widget._role == "user" else AGENT_DISPLAY_NAME
        lines.append(f"{speaker}\n{widget._content}")
    return "\n\n".join(lines)


class NemoInput(Input):
    async def on_key(self, event: events.Key) -> None:
        if event.key in ("up", "down"):
            direction = -1 if event.key == "up" else 1
            self.app.cycle_input_history(direction)  # type: ignore[attr-defined]
            event.prevent_default()
            event.stop()


class NemoApp(App):
    CSS_PATH = "tui.tcss"
    BINDINGS = [
        Binding("ctrl+c", "copy_chat", show=False, priority=True),
        Binding("ctrl+d", "close_app", show=False, priority=True),
    ]

    def __init__(self, state: RuntimeState) -> None:
        self._state = state
        self._history: list[str] = []
        self._history_idx: int = -1
        self._last_user_input: str | None = None
        self._last_interaction_widgets: list[Static] = []
        self._last_user_activity_monotonic: float | None = None
        self._vram_poll_wakeup: asyncio.Event | None = None
        self._vram_poll_task: asyncio.Task[None] | None = None
        self._messages: list[dict] = [
            {"role": "system", "content": _build_system_prompt(state)}
        ]
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static(f"◆ {AGENT_DISPLAY_NAME}", id="header-left"),
            Static(_build_header_status(self._state), id="header-right"),
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
        text.append("[ctrl+c]", style=COLOR_USER)
        text.append(" copy  ", style="#444444")
        text.append("[↑↓]", style=COLOR_NEMO)
        text.append(" history  ", style="#444444")
        text.append("[ctrl+r]", style=COLOR_USER)
        text.append(" retry", style="#444444")
        text.append("  ", style="#444444")
        text.append("[/clear]", style=COLOR_USER)
        text.append(" clear  ", style="#444444")
        text.append("[ctrl+d]", style=COLOR_NEMO)
        text.append(" exit", style="#444444")
        footer.update(text)
        self.query_one(NemoInput).focus()
        self._vram_poll_wakeup = asyncio.Event()
        self._vram_poll_task = asyncio.create_task(self._poll_vram_header())

    async def on_unmount(self) -> None:
        if self._vram_poll_task is None:
            return
        self._vram_poll_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._vram_poll_task
        self._vram_poll_task = None
        self._vram_poll_wakeup = None

    def _mark_vram_activity(self) -> None:
        self._last_user_activity_monotonic = time.monotonic()
        if self._vram_poll_wakeup is not None:
            self._vram_poll_wakeup.set()

    async def _refresh_vram_header(self) -> None:
        free_mib, total_mib = await asyncio.to_thread(load_available_vram)
        current_free = self._state.available_vram_mib
        current_total = self._state.total_vram_mib
        if (
            free_mib is not None
            and total_mib is not None
            and current_free is not None
            and current_total == total_mib
            and abs(free_mib - current_free) < VRAM_UPDATE_THRESHOLD_MIB
        ):
            return
        self._state.available_vram_mib = free_mib
        self._state.total_vram_mib = total_mib
        header_right = self.query_one("#header-right", Static)
        header_right.update(_build_header_status(self._state))

    async def _poll_vram_header(self) -> None:
        assert self._vram_poll_wakeup is not None
        await self._refresh_vram_header()
        while True:
            last_activity = self._last_user_activity_monotonic
            idle_seconds = (
                time.monotonic() - last_activity
                if last_activity is not None
                else float("inf")
            )
            interval = compute_vram_poll_interval(idle_seconds)
            try:
                await asyncio.wait_for(self._vram_poll_wakeup.wait(), timeout=interval)
            except TimeoutError:
                pass
            else:
                self._vram_poll_wakeup.clear()
            await self._refresh_vram_header()

    async def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+r":
            await self._handle_retry()
            event.prevent_default()
            event.stop()

    def action_copy_chat(self) -> None:
        self._copy_chat_to_clipboard()

    def action_close_app(self) -> None:
        self.exit()

    def cycle_input_history(self, direction: int) -> None:
        self._history_idx, value = cycle_history(
            self._history, self._history_idx, direction
        )
        inp = self.query_one(NemoInput)
        inp.value = value
        inp.cursor_position = len(value)

    async def _descend_router(self, user_message: str, router_skill) -> dict | None:
        """Walk down a router skill tree until a leaf is found, using ephemeral LLM calls."""
        current = router_skill
        while current.is_router:
            routing_messages = _build_routing_messages(user_message, current.children)
            try:
                response = await asyncio.to_thread(
                    ollama.chat, model=self._state.model, messages=routing_messages
                )
            except Exception:
                return None
            payload = _parse_skill(
                response["message"]["content"], self._state.skill_confidence_threshold
            )
            if payload is None:
                return None
            matched = next(
                (s for s in current.children if s.name == payload["skill"]), None
            )
            if matched is None:
                return None
            current = matched
        return {"skill": current.name, "confidence": 1.0}

    async def _send_message(self, user_input: str) -> None:
        msg_list = self.query_one(MessageList)
        user_widget = MessageWidget("user", user_input)
        msg_list.mount(user_widget)
        thinking = ThinkingWidget()
        msg_list.mount(thinking)
        self._messages.append({"role": "user", "content": user_input})
        msg_list.scroll_end()
        try:
            response = await asyncio.to_thread(
                ollama.chat, model=self._state.model, messages=self._messages
            )
            await thinking.remove()
            content = response["message"]["content"]
            self._messages.append({"role": "assistant", "content": content})

            # Resolve routing: descend tree if LLM picked a router skill
            resolved_skill = _parse_skill(
                content, self._state.skill_confidence_threshold
            )
            if resolved_skill:
                matched = next(
                    (
                        s
                        for s in self._state.skills
                        if s.name == resolved_skill["skill"]
                    ),
                    None,
                )
                if matched and matched.is_router:
                    resolved_skill = await self._descend_router(user_input, matched)

            response_widget = await self._mount_nemo_response(
                msg_list, content, resolved_skill
            )
            self._last_interaction_widgets = [user_widget, response_widget]
        except Exception as e:
            await thinking.remove()
            self._messages.pop()
            error_widget = MessageWidget("nemo", f"[red]Error: {e}[/red]")
            await msg_list.mount(error_widget)
            self._last_interaction_widgets = [user_widget, error_widget]
        msg_list.scroll_end()

    async def _mount_nemo_response(
        self, msg_list: MessageList, content: str, resolved_skill: dict | None = None
    ) -> MessageWidget:
        skill_json = (
            resolved_skill
            if resolved_skill is not None
            else _parse_skill(content, self._state.skill_confidence_threshold)
        )
        if skill_json:
            skill_name = skill_json["skill"]
            skill_output = await asyncio.to_thread(_run_skill, skill_name, skill_json)
            display = f"[{COLOR_USER}]✓ {skill_name}[/]"
            if self._state.debug:
                display += f"\n{content}"
            if skill_output:
                display += f"\n{skill_output}"
        else:
            display = content if self._state.debug else _strip_skill_payload(content)
            if not display.strip():
                display = "I need one more detail before I can choose a skill."
        response_widget = MessageWidget("nemo", display)
        await msg_list.mount(response_widget)
        return response_widget

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        if not user_input:
            return
        self.query_one(NemoInput).value = ""

        if user_input.lower() in ("/exit", "exit"):
            self.exit()
            return

        if user_input.lower() in ("/retry", "retry"):
            await self._handle_retry()
            return

        if user_input.lower() in ("/clear", "clear"):
            await self._handle_clear()
            return

        self._last_user_input = user_input
        self._mark_vram_activity()
        self._history.append(user_input)
        self._history_idx = -1
        await self._send_message(user_input)

    async def _handle_retry(self) -> None:
        if self._last_user_input is None:
            return
        for widget in reversed(self._last_interaction_widgets):
            await widget.remove()
        self._last_interaction_widgets = []
        if len(self._messages) >= 3:
            self._messages.pop()
            self._messages.pop()
        self._history_idx = -1
        self._mark_vram_activity()
        await self._send_message(self._last_user_input)

    async def _handle_clear(self) -> None:
        msg_list = self.query_one(MessageList)
        for widget in reversed(msg_list.children):
            await widget.remove()
        self._messages = [
            {"role": "system", "content": _build_system_prompt(self._state)}
        ]
        self._last_user_input = None
        self._last_interaction_widgets = []
        self._history_idx = -1

    def _copy_chat_to_clipboard(self) -> None:
        msg_list = self.query_one(MessageList)
        transcript = _build_chat_transcript(list(msg_list.children))
        if not transcript:
            self.notify("No chat to copy", title=AGENT_DISPLAY_NAME, severity="warning")
            return
        _write_clipboard(transcript)
        self.notify("Chat copied to clipboard", title=AGENT_DISPLAY_NAME, timeout=1.5)


def start_tui(state: RuntimeState) -> None:
    NemoApp(state).run()
