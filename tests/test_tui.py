import pytest
from mnemo8.loader import load_available_vram_mib
from mnemo8.tui import (
    ThinkingWidget,
    MessageWidget,
    _build_header_status,
    _build_chat_transcript,
    _build_system_prompt,
    _format_available_vram,
    _parse_skill,
    cycle_history,
    NemoApp,
)
from mnemo8.models import RuntimeState, Skill

# --- _parse_skill ---


def test_parse_skill_plain_json():
    content = '{"skill": "reminders", "time": "9am"}'
    assert _parse_skill(content) == {"skill": "reminders", "time": "9am"}


def test_parse_skill_in_code_block():
    content = 'Sure!\n```json\n{"skill": "calendar"}\n```'
    assert _parse_skill(content) == {"skill": "calendar"}


def test_parse_skill_missing_skill_key():
    assert _parse_skill('{"action": "remind"}') is None


def test_parse_skill_plain_text():
    assert _parse_skill("I believe Paris is the capital.") is None


def test_parse_skill_empty_string():
    assert _parse_skill("") is None


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


# --- _build_system_prompt ---


def test_build_system_prompt_base():
    state = RuntimeState(cwd="/tmp")
    prompt = _build_system_prompt(state)
    assert "mnemo8" in prompt


def test_build_system_prompt_includes_skill_content():
    state = RuntimeState(
        cwd="/tmp",
        skills=[
            Skill(name="calendar.md", path="skills/calendar.md", content="# Calendar")
        ],
    )
    prompt = _build_system_prompt(state)
    assert "calendar.md" in prompt
    assert "# Calendar" in prompt


def test_build_system_prompt_includes_agents_content():
    state = RuntimeState(cwd="/tmp", agents_content="You are Nemo.")
    prompt = _build_system_prompt(state)
    assert "You are Nemo." in prompt


def test_build_system_prompt_no_skills_omits_skill_section():
    state = RuntimeState(cwd="/tmp")
    prompt = _build_system_prompt(state)
    assert "--- Skill:" not in prompt


def test_format_available_vram_none():
    assert _format_available_vram(None) == "VRAM n/a"


def test_format_available_vram_mib():
    assert _format_available_vram(768) == "768 MiB VRAM free"


def test_format_available_vram_gib():
    assert _format_available_vram(12288) == "12.0 GiB VRAM free"


def test_build_header_status_includes_model_skills_and_vram():
    state = RuntimeState(
        cwd="/tmp",
        model="qwen3:8b",
        skills=[
            Skill(name="calendar.md", path="skills/calendar.md", content="# Calendar")
        ],
        available_vram_mib=6144,
    )

    assert _build_header_status(state) == "qwen3:8b · 1 skills · 6.0 GiB VRAM free"


def test_build_chat_transcript_uses_visible_messages_only():
    transcript = _build_chat_transcript(
        [
            MessageWidget("user", "hello"),
            ThinkingWidget(),
            MessageWidget("nemo", "hi there"),
        ]
    )

    assert transcript == "You\nhello\n\nNemo\nhi there"


def test_clear_command_resets_chat_but_keeps_input_history():
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    original_prompt = _build_system_prompt(state)
    app._messages = [
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
            self.children = []

    app.query_one = lambda *args, **kwargs: DummyMessageList()  # type: ignore[method-assign]

    import asyncio

    asyncio.run(app._handle_clear())

    assert app._messages == [{"role": "system", "content": original_prompt}]
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

    assert copied == ["You\nhello\n\nNemo\nhi there"]
    assert notifications == [("Chat copied to clipboard", "Nemo", "information")]


def test_action_copy_chat_warns_when_chat_is_empty(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)

    class DummyMessageList:
        def __init__(self) -> None:
            self.children = []

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
    assert notifications == [("No chat to copy", "Nemo", "warning")]


def test_thinking_widget_advance_frame_cycles_spinner():
    widget = ThinkingWidget()

    assert widget.render().plain == "Nemo\n⠋ thinking…"

    widget.advance_frame()
    assert widget.render().plain == "Nemo\n⠙ thinking…"

    for _ in range(len(ThinkingWidget.FRAMES) - 1):
        widget.advance_frame()

    assert widget.render().plain == "Nemo\n⠋ thinking…"


def test_load_available_vram_mib_sums_all_gpus(monkeypatch):
    class Result:
        stdout = "4096\n2048\n"

    def fake_run(*args, **kwargs):
        return Result()

    monkeypatch.setattr("mnemo8.loader.subprocess.run", fake_run)

    assert load_available_vram_mib() == 6144


def test_load_available_vram_mib_returns_none_when_command_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("mnemo8.loader.subprocess.run", fake_run)

    assert load_available_vram_mib() is None
