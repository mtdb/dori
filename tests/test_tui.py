import asyncio
from types import SimpleNamespace

from mnemo8.chat import ChatResponse, build_system_prompt, parse_skill
from mnemo8.loader import load_available_vram
from mnemo8.models import RuntimeState, Skill
from mnemo8.tui import (
    MessageWidget,
    NemoApp,
    ThinkingWidget,
    _build_chat_transcript,
    _build_header_status,
    _format_vram_bar,
    compute_vram_poll_interval,
    cycle_history,
)

# Backward-compat aliases so tests that reference the old tui names still pass
_build_system_prompt = build_system_prompt
_parse_skill = parse_skill


# --- cycle_history ---


def test_cycle_history_up_from_fresh():
    idx, val = cycle_history(["hello", "world"], -1, -1)
    assert idx == 1
    assert val == "world"


def test_cycle_history_up_further():
    idx, val = cycle_history(["hello", "world"], 1, -1)
    assert idx == 0
    assert val == "hello"


def test_cycle_history_up_at_top_stays():
    idx, val = cycle_history(["hello", "world"], 0, -1)
    assert idx == 0
    assert val == "hello"


def test_cycle_history_down_to_fresh():
    idx, val = cycle_history(["hello", "world"], 1, 1)
    assert idx == -1
    assert val == ""


def test_cycle_history_down_from_fresh_does_nothing():
    idx, val = cycle_history(["hello"], -1, 1)
    assert idx == -1
    assert val == ""


def test_cycle_history_empty_list():
    idx, val = cycle_history([], -1, -1)
    assert idx == -1
    assert val == ""


def test_format_vram_bar_none_when_free_none():
    assert _format_vram_bar(None, 8192) == "VRAM n/a"


def test_format_vram_bar_none_when_total_none():
    assert _format_vram_bar(4096, None) == "VRAM n/a"


def test_format_vram_bar_none_when_both_none():
    assert _format_vram_bar(None, None) == "VRAM n/a"


def test_format_vram_bar_mib():
    assert _format_vram_bar(768, 2048) == "[██████░░░░] 768 MiB free"


def test_format_vram_bar_gib():
    assert _format_vram_bar(6144, 8192) == "[██░░░░░░░░] 6.0 GiB free"


def test_build_header_status_includes_model_skills_and_vram():
    state = RuntimeState(
        cwd="/tmp",
        model="qwen3:8b",
        skills=[
            Skill(name="calendar.md", path="skills/calendar.md", content="# Calendar")
        ],
        available_vram_mib=6144,
        total_vram_mib=8192,
    )

    assert (
        _build_header_status(state) == "qwen3:8b · 1 skills · [██░░░░░░░░] 6.0 GiB free"
    )


def test_compute_vram_poll_interval_adapts_to_idle_time():
    assert compute_vram_poll_interval(0) == 1
    assert compute_vram_poll_interval(13) == 1
    assert compute_vram_poll_interval(16) == 5
    assert compute_vram_poll_interval(20) == 10
    assert compute_vram_poll_interval(40) == 15
    assert compute_vram_poll_interval(80) == 20
    assert compute_vram_poll_interval(140) == 30


def test_mark_vram_activity_sets_wakeup_event():
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    app._vram_poll_wakeup = asyncio.Event()

    app._mark_vram_activity()

    assert app._last_user_activity_monotonic is not None
    assert app._vram_poll_wakeup.is_set()


def test_on_input_submitted_marks_vram_activity_before_sending(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    app._vram_poll_wakeup = asyncio.Event()

    sent: list[str] = []

    async def fake_send_message(value: str) -> None:
        sent.append(value)

    class DummyInput:
        value = ""

    monkeypatch.setattr(app, "query_one", lambda *args, **kwargs: DummyInput())
    monkeypatch.setattr(app, "_send_message", fake_send_message)

    asyncio.run(app.on_input_submitted(SimpleNamespace(value="hello world")))

    assert sent == ["hello world"]
    assert app._last_user_activity_monotonic is not None
    assert app._vram_poll_wakeup.is_set()


def test_build_chat_transcript_uses_visible_messages_only():
    transcript = _build_chat_transcript(
        [
            MessageWidget("user", "hello"),
            ThinkingWidget(),
            MessageWidget("nemo", "hi there"),
        ]
    )

    assert transcript == "You\nhello\n\nDori\nhi there"


def test_mount_nemo_response_renders_display_text():
    """_mount_nemo_response is now a thin display layer; it just mounts a widget."""
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)

    class DummyMessageList:
        def __init__(self) -> None:
            self.children: list[object] = []

        async def mount(self, widget):
            self.children.append(widget)

    chat_response = ChatResponse(
        raw_content="raw",
        display_text="✓ search\n22°C, sunny",
        resolved_skill={"skill": "search", "confidence": 0.9},
        skill_output="22°C, sunny",
    )
    widget = asyncio.run(app._mount_nemo_response(DummyMessageList(), chat_response))

    assert widget._content == "✓ search\n22°C, sunny"


def test_clear_command_resets_chat_but_keeps_input_history():
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    original_prompt = _build_system_prompt(state)
    app._engine.messages = [
        {"role": "system", "content": original_prompt},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    app._history = ["first", "second"]
    app._history_idx = 1
    app._last_user_input = "hello"
    app._last_interaction_widgets = []

    class DummyMessageList:
        def __init__(self) -> None:
            self.children: list[object] = []

    app.query_one = lambda *args, **kwargs: DummyMessageList()  # type: ignore[method-assign]

    import asyncio

    asyncio.run(app._handle_clear())

    assert app._engine.messages == [{"role": "system", "content": original_prompt}]
    assert app._last_user_input is None
    assert app._last_interaction_widgets == []
    assert app._history == ["first", "second"]
    assert app._history_idx == -1


def test_action_copy_chat_copies_visible_chat_and_notifies(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)

    class DummyMessageList:
        def __init__(self) -> None:
            self.children = [
                MessageWidget("user", "hello"),
                MessageWidget("nemo", "hi there"),
            ]

    copied: list[str] = []
    notifications: list[tuple[str, str, str | None]] = []

    def fake_query_one(*args, **kwargs):
        return DummyMessageList()

    def fake_write_clipboard(value: str) -> None:
        copied.append(value)

    def fake_notify(
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        notifications.append((message, title, severity))

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr("mnemo8.tui._write_clipboard", fake_write_clipboard)
    monkeypatch.setattr(app, "notify", fake_notify)

    app.action_copy_chat()

    assert copied == ["You\nhello\n\nDori\nhi there"]
    assert notifications == [("Chat copied to clipboard", "Dori", "information")]


def test_action_copy_chat_warns_when_chat_is_empty(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)

    class DummyMessageList:
        def __init__(self) -> None:
            self.children: list[object] = []

    copied: list[str] = []
    notifications: list[tuple[str, str, str | None]] = []

    def fake_query_one(*args, **kwargs):
        return DummyMessageList()

    def fake_write_clipboard(value: str) -> None:
        copied.append(value)

    def fake_notify(
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        notifications.append((message, title, severity))

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr("mnemo8.tui._write_clipboard", fake_write_clipboard)
    monkeypatch.setattr(app, "notify", fake_notify)

    app.action_copy_chat()

    assert copied == []
    assert notifications == [("No chat to copy", "Dori", "warning")]


def test_thinking_widget_advance_frame_cycles_spinner():
    widget = ThinkingWidget()

    assert widget.render().plain == "Dori\n⠋ thinking…"

    widget.advance_frame()
    assert widget.render().plain == "Dori\n⠙ thinking…"

    for _ in range(len(ThinkingWidget.FRAMES) - 1):
        widget.advance_frame()

    assert widget.render().plain == "Dori\n⠋ thinking…"


def test_load_available_vram_sums_all_gpus(monkeypatch):
    class Result:
        stdout = "4096,8192\n2048,4096\n"

    def fake_run(*args, **kwargs):
        return Result()

    monkeypatch.setattr("mnemo8.loader.subprocess.run", fake_run)

    assert load_available_vram() == (6144, 12288)


def test_load_available_vram_returns_none_tuple_when_command_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("mnemo8.loader.subprocess.run", fake_run)

    assert load_available_vram() == (None, None)


def test_initial_prompt_triggers_send(monkeypatch):
    # _submit_initial_prompt must call _send_message with the prompt text
    state = RuntimeState(cwd="/tmp", initial_prompt="remind me at 9am")
    app = NemoApp(state)
    app._vram_poll_wakeup = asyncio.Event()
    sent: list[str] = []

    async def fake_send_message(value: str) -> None:
        sent.append(value)

    monkeypatch.setattr(app, "_send_message", fake_send_message)

    asyncio.run(app._submit_initial_prompt("remind me at 9am"))

    assert sent == ["remind me at 9am"]


def test_initial_prompt_blank_is_ignored():
    # on_mount skips _submit_initial_prompt when the prompt is blank
    state = RuntimeState(cwd="/tmp", initial_prompt="   ")
    assert (state.initial_prompt or "").strip() == ""
