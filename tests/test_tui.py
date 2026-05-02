import asyncio

import pytest
from types import SimpleNamespace
from mnemo8.loader import load_available_vram
from mnemo8.tui import (
    ThinkingWidget,
    MessageWidget,
    _build_header_status,
    _build_chat_transcript,
    _build_system_prompt,
    compute_vram_poll_interval,
    _format_vram_bar,
    _parse_skill,
    cycle_history,
    NemoApp,
)
from mnemo8.models import RuntimeState, Skill

# --- _parse_skill ---


def test_parse_skill_plain_json():
    content = '{"skill": "reminders", "time": "9am", "confidence": 0.95}'
    assert _parse_skill(content) == {
        "skill": "reminders",
        "time": "9am",
        "confidence": 0.95,
    }


def test_parse_skill_in_code_block():
    content = '```json\n{"skill": "calendar", "confidence": 0.85}\n```'
    assert _parse_skill(content) == {"skill": "calendar", "confidence": 0.85}


def test_parse_skill_missing_skill_key():
    assert _parse_skill('{"action": "remind", "confidence": 0.9}') is None


def test_parse_skill_missing_confidence_uses_legacy_standalone_json():
    assert _parse_skill('{"skill": "reminders", "time": "9am"}') == {
        "skill": "reminders",
        "time": "9am",
        "confidence": 1.0,
    }


def test_parse_skill_missing_confidence_with_prose_is_ignored():
    assert (
        _parse_skill('Claro:\n```json\n{"skill": "reminders", "time": "9am"}\n```')
        is None
    )


def test_parse_skill_below_threshold_is_ignored():
    content = '{"skill": "search", "query": "shakira", "confidence": 0.79}'
    assert _parse_skill(content, min_confidence=0.8) is None


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
    assert "confidence" in prompt


def test_build_system_prompt_includes_agents_content():
    state = RuntimeState(cwd="/tmp", agents_content="You are Dori.")
    prompt = _build_system_prompt(state)
    assert "You are Dori." in prompt


def test_build_system_prompt_no_skills_omits_skill_section():
    state = RuntimeState(cwd="/tmp")
    prompt = _build_system_prompt(state)
    assert "--- Skill:" not in prompt


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


def test_mount_nemo_response_executes_high_confidence_skill_without_json(monkeypatch):
    state = RuntimeState(cwd="/tmp", skill_confidence_threshold=0.8)
    app = NemoApp(state)

    class DummyMessageList:
        def __init__(self) -> None:
            self.children: list[object] = []

        async def mount(self, widget):
            self.children.append(widget)

    monkeypatch.setattr("mnemo8.tui._run_skill", lambda name, payload: "Madrid, 20 Nov")

    import asyncio

    widget = asyncio.run(
        app._mount_nemo_response(
            DummyMessageList(),
            '{"skill": "search", "query": "Shakira concert Madrid", "confidence": 0.92}',
        )
    )

    assert "✓ search" in widget._content
    assert "Madrid, 20 Nov" in widget._content
    assert '"skill": "search"' not in widget._content


def test_mount_nemo_response_executes_legacy_standalone_json(monkeypatch):
    state = RuntimeState(cwd="/tmp", skill_confidence_threshold=0.8)
    app = NemoApp(state)

    class DummyMessageList:
        def __init__(self) -> None:
            self.children: list[object] = []

        async def mount(self, widget):
            self.children.append(widget)

    monkeypatch.setattr(
        "mnemo8.tui._run_skill", lambda name, payload: "recordatorio creado"
    )

    import asyncio

    widget = asyncio.run(
        app._mount_nemo_response(
            DummyMessageList(),
            '{"skill": "reminders", "message": "salir a correr", "when": "en 10 minutos"}',
        )
    )

    assert "✓ reminders" in widget._content
    assert "recordatorio creado" in widget._content
    assert '"skill": "reminders"' not in widget._content


def test_mount_nemo_response_shows_json_in_debug_mode(monkeypatch):
    state = RuntimeState(cwd="/tmp", debug=True, skill_confidence_threshold=0.8)
    app = NemoApp(state)

    class DummyMessageList:
        def __init__(self) -> None:
            self.children: list[object] = []

        async def mount(self, widget):
            self.children.append(widget)

    monkeypatch.setattr("mnemo8.tui._run_skill", lambda name, payload: "Madrid, 20 Nov")

    import asyncio

    widget = asyncio.run(
        app._mount_nemo_response(
            DummyMessageList(),
            '{"skill": "search", "query": "Shakira concert Madrid", "confidence": 0.92}',
        )
    )

    assert '"skill": "search"' in widget._content


def test_mount_nemo_response_hides_low_confidence_payload(monkeypatch):
    state = RuntimeState(cwd="/tmp", skill_confidence_threshold=0.8)
    app = NemoApp(state)
    executed: list[str] = []

    class DummyMessageList:
        def __init__(self) -> None:
            self.children: list[object] = []

        async def mount(self, widget):
            self.children.append(widget)

    def fake_run_skill(name, payload):
        executed.append(name)
        return "should not run"

    monkeypatch.setattr("mnemo8.tui._run_skill", fake_run_skill)

    import asyncio

    widget = asyncio.run(
        app._mount_nemo_response(
            DummyMessageList(),
            'Necesito confirmar la fecha exacta.\n```json\n{"skill": "search", "query": "Shakira concert Madrid", "confidence": 0.42}\n```',
        )
    )

    assert executed == []
    assert widget._content == "Necesito confirmar la fecha exacta."


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
            self.children: list[object] = []

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
