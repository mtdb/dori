import asyncio
from types import SimpleNamespace

from dori.chat import ChatResponse, build_system_prompt, parse_skill
from dori.loader import load_available_vram
from dori.models import RuntimeState, Skill
from dori.tui import (
    MessageWidget,
    NemoApp,
    ThinkingWidget,
    _build_chat_transcript,
    _build_header_status,
    _format_vram_bar,
    append_input_history,
    compute_vram_poll_interval,
    cycle_history,
    load_input_history,
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


def test_load_input_history_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)

    assert load_input_history() == []


def test_load_input_history_decodes_json_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)
    (tmp_path / ".history").write_text(
        '"hello world"\n"line\\nbreak"\n',
        encoding="utf-8",
    )

    assert load_input_history() == ["hello world", "line\nbreak"]


def test_load_input_history_ignores_invalid_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)
    (tmp_path / ".history").write_text(
        '"first"\nnot json\n42\n""\n"last"\n',
        encoding="utf-8",
    )

    assert load_input_history() == ["first", "last"]


def test_append_input_history_keeps_last_100_messages(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)

    for index in range(105):
        append_input_history(f"message {index}")

    assert load_input_history() == [f"message {index}" for index in range(5, 105)]


def test_nemo_app_starts_with_persistent_input_history(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)
    (tmp_path / ".history").write_text('"first"\n"second"\n', encoding="utf-8")

    app = NemoApp(RuntimeState(cwd="/tmp"))

    assert app._history == ["first", "second"]


def test_submit_initial_prompt_persists_input_history(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)
    state = RuntimeState(cwd="/tmp", initial_prompt="remind me at 9am")
    app = NemoApp(state)
    app._vram_poll_wakeup = asyncio.Event()

    async def fake_send_message(value: str) -> None:
        pass

    monkeypatch.setattr(app, "_send_message", fake_send_message)

    asyncio.run(app._submit_initial_prompt("remind me at 9am"))

    assert load_input_history() == ["remind me at 9am"]


def test_on_input_submitted_persists_normal_messages(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)
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
    assert load_input_history() == ["hello world"]


def test_on_input_submitted_routes_to_active_workflow(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    app._vram_poll_wakeup = asyncio.Event()
    answers: list[str] = []

    async def fake_send_message(value: str) -> None:
        raise AssertionError("normal send should not run while workflow is active")

    async def fake_answer_workflow(value: str) -> ChatResponse:
        answers.append(value)
        return ChatResponse(
            raw_content="",
            display_text="✓ workflow\nCommitted.",
            resolved_skill=None,
            skill_output="Committed.",
        )

    app._engine = SimpleNamespace(
        has_active_workflow=True,
        answer_workflow=fake_answer_workflow,
    )
    monkeypatch.setattr(app, "_send_message", fake_send_message)
    monkeypatch.setattr(
        app, "query_one", lambda *args, **kwargs: SimpleNamespace(value="")
    )
    routed: list[tuple[str, object]] = []

    async def fake_run_user_turn(user_input: str, responder) -> None:
        routed.append((user_input, responder))
        await responder(user_input)

    monkeypatch.setattr(app, "_run_user_turn", fake_run_user_turn)

    asyncio.run(app.on_input_submitted(SimpleNamespace(value="yes")))

    assert answers == ["yes"]
    assert load_input_history() == ["yes"]


def test_on_input_submitted_cancels_active_workflow_without_persisting(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    app._vram_poll_wakeup = asyncio.Event()
    cancelled: list[bool] = []

    async def fake_cancel_workflow() -> ChatResponse:
        cancelled.append(True)
        return ChatResponse(
            raw_content="",
            display_text="Workflow cancelled.",
            resolved_skill=None,
            skill_output=None,
        )

    app._engine = SimpleNamespace(
        has_active_workflow=True,
        cancel_workflow=fake_cancel_workflow,
    )
    monkeypatch.setattr(
        app, "query_one", lambda *args, **kwargs: SimpleNamespace(value="")
    )
    routed: list[str] = []

    async def fake_run_user_turn(user_input: str, responder) -> None:
        routed.append(user_input)
        await responder(user_input)

    monkeypatch.setattr(app, "_run_user_turn", fake_run_user_turn)

    asyncio.run(app.on_input_submitted(SimpleNamespace(value="/cancel")))

    assert cancelled == [True]
    assert routed == ["/cancel"]
    assert load_input_history() == []


def test_clear_command_keeps_persistent_input_history(tmp_path, monkeypatch):
    monkeypatch.setattr("dori.tui.get_runtime_home", lambda: tmp_path)
    append_input_history("first")
    app = NemoApp(RuntimeState(cwd="/tmp"))

    class DummyMessageList:
        def __init__(self) -> None:
            self.children: list[object] = []

    app.query_one = lambda *args, **kwargs: DummyMessageList()  # type: ignore[method-assign]

    asyncio.run(app._handle_clear())

    assert load_input_history() == ["first"]


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


def test_retry_is_blocked_while_workflow_is_active(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    app._last_user_input = "hello again"
    notifications: list[tuple[str, str, str | None]] = []

    def fake_notify(
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        notifications.append((message, title, severity))

    app._engine = SimpleNamespace(has_active_workflow=True)
    monkeypatch.setattr(app, "notify", fake_notify)

    asyncio.run(app._handle_retry())

    assert notifications == [
        ("Finish the active workflow or use /cancel first", "Dori", "warning")
    ]


def test_translate_input_blank_is_noop(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)

    class DummyInput:
        value = "   "
        cursor_position = 0

    class FakeEngine:
        called = False

        async def translate_to_english(self, text: str) -> str:
            self.called = True
            return text

    fake_engine = FakeEngine()
    app._engine = fake_engine
    monkeypatch.setattr(app, "query_one", lambda *args, **kwargs: DummyInput())

    asyncio.run(app._handle_translate_input())

    assert fake_engine.called is False


def test_translate_is_blocked_while_workflow_is_active(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    notifications: list[tuple[str, str, str | None]] = []

    class DummyInput:
        value = "Resume esta carpeta."
        cursor_position = 0

    def fake_notify(
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        notifications.append((message, title, severity))

    app._engine = SimpleNamespace(has_active_workflow=True)
    monkeypatch.setattr(app, "query_one", lambda *args, **kwargs: DummyInput())
    monkeypatch.setattr(app, "notify", fake_notify)

    asyncio.run(app._handle_translate_input())

    assert notifications == [
        ("Finish the active workflow or use /cancel first", "Dori", "warning")
    ]


def test_translate_input_replaces_value_and_cursor(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    app._vram_poll_wakeup = asyncio.Event()
    dummy_input = SimpleNamespace(value="Resume esta carpeta.", cursor_position=0)
    prompt_updates: list[object] = []

    class DummyPromptLabel:
        def update(self, value) -> None:
            prompt_updates.append(value)

    class FakeEngine:
        async def translate_to_english(self, text: str) -> str:
            assert text == "Resume esta carpeta."
            return "Summarize this folder."

    app._engine = FakeEngine()

    def fake_query_one(selector, *args, **kwargs):
        if selector == "#prompt-label":
            return DummyPromptLabel()
        return dummy_input

    monkeypatch.setattr(app, "query_one", fake_query_one)

    asyncio.run(app._handle_translate_input())

    assert dummy_input.value == "Summarize this folder."
    assert dummy_input.cursor_position == len("Summarize this folder.")
    assert app._last_user_activity_monotonic is not None
    assert app._vram_poll_wakeup.is_set()
    assert prompt_updates[0] == "⠋"
    assert prompt_updates[-1] == "❯"


def test_translate_input_failure_keeps_original_and_notifies(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    dummy_input = SimpleNamespace(value="Hola mundo", cursor_position=3)
    notifications: list[tuple[str, str, str | None]] = []
    prompt_updates: list[object] = []

    class DummyPromptLabel:
        def update(self, value) -> None:
            prompt_updates.append(value)

    class FakeEngine:
        async def translate_to_english(self, text: str) -> str:
            raise RuntimeError("conn failed")

    def fake_notify(
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        notifications.append((message, title, severity))

    app._engine = FakeEngine()

    def fake_query_one(selector, *args, **kwargs):
        if selector == "#prompt-label":
            return DummyPromptLabel()
        return dummy_input

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(app, "notify", fake_notify)

    asyncio.run(app._handle_translate_input())

    assert dummy_input.value == "Hola mundo"
    assert dummy_input.cursor_position == 3
    assert prompt_updates[0] == "⠋"
    assert prompt_updates[-1] == "❯"
    assert notifications == [("Translation failed: conn failed", "Dori", "error")]


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


def test_ctrl_r_starts_retry_edit_mode_and_cleans_last_exchange(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    app._last_user_input = "hello again"
    app._history_idx = 1
    original_messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    app._engine.messages = list(original_messages)

    class DummyWidget:
        def __init__(self) -> None:
            self.removed = False

        async def remove(self) -> None:
            self.removed = True

    widgets = [DummyWidget(), DummyWidget()]
    app._last_interaction_widgets = widgets

    class DummyInput:
        def __init__(self) -> None:
            self.value = ""
            self.cursor_position = 0

    event = SimpleNamespace(
        key="ctrl+r",
        prevent_default=lambda: None,
        stop=lambda: None,
    )
    dummy_input = DummyInput()
    monkeypatch.setattr(app, "query_one", lambda *args, **kwargs: dummy_input)

    asyncio.run(app.on_key(event))

    assert dummy_input.value == "hello again"
    assert dummy_input.cursor_position == len("hello again")
    assert app._history_idx == -1
    assert app._engine.messages == [{"role": "system", "content": "sys"}]
    assert app._last_interaction_widgets == []
    assert all(widget.removed for widget in widgets)


def test_ctrl_r_is_blocked_while_workflow_is_active(monkeypatch):
    state = RuntimeState(cwd="/tmp")
    app = NemoApp(state)
    app._last_user_input = "hello again"
    notifications: list[tuple[str, str, str | None]] = []

    def fake_notify(
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        notifications.append((message, title, severity))

    event = SimpleNamespace(
        key="ctrl+r",
        prevent_default=lambda: None,
        stop=lambda: None,
    )
    app._engine = SimpleNamespace(has_active_workflow=True)
    monkeypatch.setattr(app, "notify", fake_notify)

    asyncio.run(app.on_key(event))

    assert notifications == [
        ("Finish the active workflow or use /cancel first", "Dori", "warning")
    ]


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
    monkeypatch.setattr("dori.tui._write_clipboard", fake_write_clipboard)
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
    monkeypatch.setattr("dori.tui._write_clipboard", fake_write_clipboard)
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

    monkeypatch.setattr("dori.loader.subprocess.run", fake_run)

    assert load_available_vram() == (6144, 12288)


def test_load_available_vram_returns_none_tuple_when_command_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("dori.loader.subprocess.run", fake_run)

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
