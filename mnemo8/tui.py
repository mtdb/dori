"""
TUI layer for mnemo8.

All business logic (LLM calls, skill resolution, display-text construction)
lives in mnemo8.chat.  This module is responsible only for the Textual UI:
widgets, layout, user input, VRAM header, clipboard, and triggering the
conversation engine.
"""

import asyncio
import json
import math
import os
import subprocess
import sys
import time
from contextlib import suppress

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Input, Static

from mnemo8.chat import (
    ChatResponse,
    ConversationEngine,
    build_system_prompt,
    parse_skill,
    run_skill,
)
from mnemo8.loader import get_runtime_home, load_available_vram
from mnemo8.models import RuntimeState

# ---------------------------------------------------------------------------
# Backward-compat aliases used by existing tests
# ---------------------------------------------------------------------------
_build_system_prompt = build_system_prompt
_parse_skill = parse_skill
_run_skill = run_skill

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLOR_USER = "#6fc3df"
COLOR_NEMO = "#f38518"
COLOR_THINKING = "#555555"
AGENT_DISPLAY_NAME = "Dori"
INPUT_HISTORY_FILENAME = ".history"
INPUT_HISTORY_LIMIT = 100
VRAM_POLL_BURST_WINDOW_SECONDS = 13.0
VRAM_POLL_TAU_SECONDS = 60.0
VRAM_POLL_BUCKETS = (1, 5, 10, 15, 20, 30)
VRAM_UPDATE_THRESHOLD_MIB = 64


# ---------------------------------------------------------------------------
# Pure UI helpers
# ---------------------------------------------------------------------------


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
    total = 0
    for s in skills:
        if s.is_router:
            total += _count_leaf_skills(s.children)
        else:
            total += 1
    return total


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


def load_input_history(limit: int = INPUT_HISTORY_LIMIT) -> list[str]:
    history_path = get_runtime_home() / INPUT_HISTORY_FILENAME
    if not history_path.is_file():
        return []

    messages: list[str] = []
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []

    for line in lines:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, str) and message:
            messages.append(message)
    return messages[-limit:]


def append_input_history(
    message: str,
    limit: int = INPUT_HISTORY_LIMIT,
) -> list[str]:
    history_path = get_runtime_home() / INPUT_HISTORY_FILENAME
    history = [*load_input_history(limit), message][-limit:]
    serialized = "\n".join(json.dumps(entry) for entry in history)
    if serialized:
        serialized += "\n"

    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(serialized, encoding="utf-8")
    except OSError:
        pass
    return history


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
        self._engine = ConversationEngine(state)
        self._history: list[str] = load_input_history()
        self._history_idx: int = -1
        self._last_user_input: str | None = None
        self._last_interaction_widgets: list[Static] = []
        self._last_user_activity_monotonic: float | None = None
        self._vram_poll_wakeup: asyncio.Event | None = None
        self._vram_poll_task: asyncio.Task[None] | None = None
        super().__init__()

    # Keep _messages as a property so legacy tests that read/write it still work
    @property
    def _messages(self) -> list[dict]:
        return self._engine.messages

    @_messages.setter
    def _messages(self, value: list[dict]) -> None:
        self._engine.messages = value

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

        # Auto-submit initial prompt if present
        prompt = (self._state.initial_prompt or "").strip()
        if prompt:
            # Defer to next event loop tick so UI is ready
            asyncio.create_task(self._submit_initial_prompt(prompt))

    async def _submit_initial_prompt(self, prompt: str) -> None:
        self._last_user_input = prompt
        self._mark_vram_activity()
        self._history = append_input_history(prompt)
        self._history_idx = -1
        await self._send_message(prompt)

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

    async def _send_message(self, user_input: str) -> None:
        msg_list = self.query_one(MessageList)
        user_widget = MessageWidget("user", user_input)
        await msg_list.mount(user_widget)
        thinking = ThinkingWidget()
        await msg_list.mount(thinking)
        msg_list.scroll_end()
        try:
            chat_response = await self._engine.send(user_input)
            await thinking.remove()
            response_widget = await self._mount_nemo_response(msg_list, chat_response)
            self._last_interaction_widgets = [user_widget, response_widget]
        except Exception as e:
            await thinking.remove()
            error_widget = MessageWidget("nemo", f"[red]Error: {e}[/red]")
            await msg_list.mount(error_widget)
            self._last_interaction_widgets = [user_widget, error_widget]
        msg_list.scroll_end()

    async def _mount_nemo_response(
        self, msg_list: MessageList, response: ChatResponse
    ) -> MessageWidget:
        """Mount a MessageWidget for the given ChatResponse and return it."""
        widget = MessageWidget("nemo", response.display_text)
        await msg_list.mount(widget)
        return widget

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
        self._history = append_input_history(user_input)
        self._history_idx = -1
        await self._send_message(user_input)

    async def _handle_retry(self) -> None:
        if self._last_user_input is None:
            return
        for widget in reversed(self._last_interaction_widgets):
            await widget.remove()
        self._last_interaction_widgets = []
        self._engine.pop_last_exchange()
        self._history_idx = -1
        self._mark_vram_activity()
        await self._send_message(self._last_user_input)

    async def _handle_clear(self) -> None:
        msg_list = self.query_one(MessageList)
        for widget in reversed(msg_list.children):
            await widget.remove()
        self._engine.reset()
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
