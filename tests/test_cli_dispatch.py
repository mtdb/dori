import sys

import pytest

from dori.chat import ChatResponse
from dori.main import _run_inline, run, run_cli_skill
from dori.models import RuntimeState, Skill


def test_cli_dispatches_skill_name_to_runtime_script(tmp_path, monkeypatch, capfd):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "commit.py"
    script.write_text(
        "import json\n"
        "import sys\n"
        "payload = json.loads(sys.argv[1])\n"
        "print(f\"{payload['skill']} from cli={payload['cli']}\")\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("dori.main.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["dori", "commit"])

    with pytest.raises(SystemExit) as exit_info:
        run()

    assert exit_info.value.code == 0
    assert capfd.readouterr().out.strip() == "commit from cli=True"


def test_cli_dispatch_reports_missing_skill_script(tmp_path, monkeypatch, capsys):
    (tmp_path / "scripts").mkdir()
    monkeypatch.setattr("dori.main.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["dori", "unknown-skill"])

    with pytest.raises(SystemExit) as exit_info:
        run()

    assert exit_info.value.code == 1
    assert "Script for skill 'unknown-skill' not found" in capsys.readouterr().err


def test_cli_dispatch_does_not_execute_private_helper_scripts(
    tmp_path, monkeypatch, capsys
):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "_helper.py").write_text(
        "print('should not run')\n", encoding="utf-8"
    )
    monkeypatch.setattr("dori.main.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["dori", "_helper"])

    with pytest.raises(SystemExit) as exit_info:
        run()

    captured = capsys.readouterr()
    assert exit_info.value.code == 1
    assert "should not run" not in captured.out
    assert "Script for skill '_helper' not found" in captured.err


def test_cli_skill_inherits_terminal_for_interactive_scripts(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "commit.py"
    script.write_text("print('interactive')\n", encoding="utf-8")
    calls = []

    class FakeProcess:
        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakeProcess()

    monkeypatch.setattr("dori.main.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr("dori.main.subprocess.Popen", fake_popen)

    assert run_cli_skill("commit", [], str(tmp_path)) == 0

    _, kwargs = calls[0]
    assert "capture_output" not in kwargs
    assert "text" not in kwargs


def test_cli_skill_returns_130_when_wait_is_interrupted(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "commit.py").write_text("print('interactive')\n", encoding="utf-8")

    class FakeProcess:
        def __init__(self):
            self.wait_calls = 0

        def wait(self, timeout=None):
            self.wait_calls += 1
            if timeout is None:
                raise KeyboardInterrupt
            return 130

    process = FakeProcess()

    def fake_popen(cmd, **kwargs):
        return process

    monkeypatch.setattr("dori.main.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr("dori.main.subprocess.Popen", fake_popen)

    assert run_cli_skill("commit", [], str(tmp_path)) == 130
    assert process.wait_calls == 2


def test_cli_dispatches_update_command(monkeypatch):
    called = []

    def fake_update_workspace(cwd):
        called.append(cwd)

    monkeypatch.setattr("dori.main.update_workspace", fake_update_workspace)
    monkeypatch.setattr("dori.main.os.getcwd", lambda: "/tmp/dori-project")
    monkeypatch.setattr(sys, "argv", ["dori", "update"])

    run()

    assert called == ["/tmp/dori-project"]


def test_run_inline_enables_script_interaction(monkeypatch, capsys):
    seen: list[bool] = []

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            seen.append(allow_script_interaction)

        async def send(self, prompt: str) -> ChatResponse:
            return ChatResponse(
                raw_content="",
                display_text="done",
                resolved_skill=None,
                skill_output=None,
            )

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)

    _run_inline(RuntimeState(cwd="/tmp"), "hello")

    assert seen == [True]
    assert capsys.readouterr().out.strip() == "done"


def test_run_inline_prints_bracketed_url_text_verbatim(monkeypatch, capsys):
    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            pass

        async def send(self, prompt: str) -> ChatResponse:
            return ChatResponse(
                raw_content="",
                display_text=(
                    "Sources:\n"
                    "- [www.nvidia.com/deep-learning-institute]"
                    "(https://www.nvidia.com/deep-learning-institute)"
                ),
                resolved_skill=None,
                skill_output=None,
            )

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)

    _run_inline(RuntimeState(cwd="/tmp"), "hello")

    assert (
        capsys.readouterr().out.strip()
        == "Sources:\n- [www.nvidia.com/deep-learning-institute](https://www.nvidia.com/deep-learning-institute)"
    )


def test_run_inline_answers_pending_workflow(monkeypatch, capsys):
    events: list[tuple[str, str]] = []

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            events.append(("stdin", "readline"))
            return "confirm\n"

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            events.append(("engine", f"interactive={allow_script_interaction}"))

        async def send(self, prompt: str) -> ChatResponse:
            events.append(("engine", f"send:{prompt}"))
            return ChatResponse(
                raw_content="",
                display_text="Schedule reminder? (1. confirm, 2. cancel)",
                resolved_skill={"skill": "reminders"},
                skill_output=None,
                workflow_pending=True,
            )

        async def answer_workflow(self, value: str) -> ChatResponse:
            events.append(("engine", f"answer:{value}"))
            return ChatResponse(
                raw_content="",
                display_text="[D-Bus]: Scheduled reminder for 'call pablo' in 1 minute.",
                resolved_skill={"skill": "workflow"},
                skill_output=None,
                workflow_pending=False,
            )

        async def close(self) -> None:
            events.append(("engine", "close"))

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())

    _run_inline(RuntimeState(cwd="/tmp"), "remind me in one minute to call pablo")

    assert events == [
        ("engine", "interactive=True"),
        ("engine", "send:remind me in one minute to call pablo"),
        ("stdin", "readline"),
        ("engine", "answer:confirm"),
        ("engine", "close"),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "Schedule reminder? (1. confirm, 2. cancel)",
        "[D-Bus]: Scheduled reminder for 'call pablo' in 1 minute.",
    ]


def test_run_inline_answers_ask_workflow(monkeypatch, capsys):
    events: list[tuple[str, str]] = []

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            events.append(("stdin", "readline"))
            return "Mauricio\n"

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            events.append(("engine", f"interactive={allow_script_interaction}"))

        async def send(self, prompt: str) -> ChatResponse:
            events.append(("engine", f"send:{prompt}"))
            return ChatResponse(
                raw_content="",
                display_text="What is your name?",
                resolved_skill={"skill": "asker"},
                skill_output=None,
                workflow_pending=True,
            )

        async def answer_workflow(self, value: str) -> ChatResponse:
            events.append(("engine", f"answer:{value}"))
            return ChatResponse(
                raw_content="",
                display_text="Hello, Mauricio.",
                resolved_skill={"skill": "workflow"},
                skill_output=None,
                workflow_pending=False,
            )

        async def close(self) -> None:
            events.append(("engine", "close"))

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())

    _run_inline(RuntimeState(cwd="/tmp"), "ask my name")

    assert events == [
        ("engine", "interactive=True"),
        ("engine", "send:ask my name"),
        ("stdin", "readline"),
        ("engine", "answer:Mauricio"),
        ("engine", "close"),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "What is your name?",
        "Hello, Mauricio.",
    ]


def test_run_inline_answers_confirm_workflow(monkeypatch, capsys):
    events: list[tuple[str, str]] = []

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            events.append(("stdin", "readline"))
            return "yes\n"

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            events.append(("engine", f"interactive={allow_script_interaction}"))

        async def send(self, prompt: str) -> ChatResponse:
            events.append(("engine", f"send:{prompt}"))
            return ChatResponse(
                raw_content="",
                display_text="Proceed with deployment? (Y/n)",
                resolved_skill={"skill": "deployer"},
                skill_output=None,
                workflow_pending=True,
            )

        async def answer_workflow(self, value: str) -> ChatResponse:
            events.append(("engine", f"answer:{value}"))
            return ChatResponse(
                raw_content="",
                display_text="Deployment approved.",
                resolved_skill={"skill": "workflow"},
                skill_output=None,
                workflow_pending=False,
            )

        async def close(self) -> None:
            events.append(("engine", "close"))

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())

    _run_inline(RuntimeState(cwd="/tmp"), "deploy this")

    assert events == [
        ("engine", "interactive=True"),
        ("engine", "send:deploy this"),
        ("stdin", "readline"),
        ("engine", "answer:yes"),
        ("engine", "close"),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "Proceed with deployment? (Y/n)",
        "Deployment approved.",
    ]


def test_run_inline_answers_multiple_sequential_workflow_requests(monkeypatch, capsys):
    events: list[tuple[str, str]] = []
    answers = iter(["Mauricio\n", "confirm\n"])

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            events.append(("stdin", "readline"))
            return next(answers)

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            events.append(("engine", f"interactive={allow_script_interaction}"))

        async def send(self, prompt: str) -> ChatResponse:
            events.append(("engine", f"send:{prompt}"))
            return ChatResponse(
                raw_content="",
                display_text="What is your name?",
                resolved_skill={"skill": "wizard"},
                skill_output=None,
                workflow_pending=True,
            )

        async def answer_workflow(self, value: str) -> ChatResponse:
            events.append(("engine", f"answer:{value}"))
            if value == "Mauricio":
                return ChatResponse(
                    raw_content="",
                    display_text="Create reminder for Mauricio? (1. confirm, 2. cancel)",
                    resolved_skill={"skill": "workflow"},
                    skill_output=None,
                    workflow_pending=True,
                )
            return ChatResponse(
                raw_content="",
                display_text="Reminder created for Mauricio.",
                resolved_skill={"skill": "workflow"},
                skill_output=None,
                workflow_pending=False,
            )

        async def close(self) -> None:
            events.append(("engine", "close"))

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())

    _run_inline(RuntimeState(cwd="/tmp"), "set up a reminder")

    assert events == [
        ("engine", "interactive=True"),
        ("engine", "send:set up a reminder"),
        ("stdin", "readline"),
        ("engine", "answer:Mauricio"),
        ("stdin", "readline"),
        ("engine", "answer:confirm"),
        ("engine", "close"),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "What is your name?",
        "Create reminder for Mauricio? (1. confirm, 2. cancel)",
        "Reminder created for Mauricio.",
    ]


def test_run_inline_supports_reminder_confirmation_workflow(
    tmp_path, monkeypatch, capsys
):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "reminders.py").write_text(
        "import json\n"
        "import sys\n"
        "from dori.script import choose\n"
        "payload = json.loads(sys.argv[1])\n"
        "if choose("
        "f\"Schedule reminder '{payload['message']}' for {payload['when']}?\", "
        "['confirm', 'cancel']) == 'confirm':\n"
        "    print(f\"scheduled {payload['message']} {payload['when']}\")\n"
        "else:\n"
        "    print('cancelled')\n",
        encoding="utf-8",
    )

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            nonlocal workflow_started
            workflow_started = True
            return "1\n"

    model_calls = 0
    workflow_started = False

    def fake_chat_with_model(state, messages):
        nonlocal model_calls
        if workflow_started:
            pytest.fail("model called again after workflow started")
        model_calls += 1
        return {
            "message": {
                "content": (
                    '{"skill":"reminders","confidence":1.0,'
                    '"message":"call pablo","when":"in 1 minute",'
                    '"raw_text":"remind me in one minute to call pablo"}'
                )
            }
        }

    monkeypatch.setattr("dori.main.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr("dori.chat.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())
    monkeypatch.setattr("dori.chat._chat_with_model", fake_chat_with_model)

    _run_inline(
        RuntimeState(
            cwd=str(tmp_path),
            skills=[
                Skill(
                    name="reminders",
                    path="skills/reminders.md",
                    content="# Reminders\nSchedule reminders.",
                )
            ],
        ),
        "remind me in one minute to call pablo",
    )

    output_lines = capsys.readouterr().out.splitlines()
    assert model_calls == 1
    assert output_lines == [
        "Schedule reminder 'call pablo' for in 1 minute? (1. confirm, 2. cancel)",
        "✓ workflow",
        "scheduled call pablo in 1 minute",
    ]


def test_run_inline_reprompts_after_invalid_workflow_answer(monkeypatch, capsys):
    answers = iter(["docs\n", "confirm\n"])
    prompts: list[str] = []

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return next(answers)

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            pass

        async def send(self, prompt: str) -> ChatResponse:
            return ChatResponse(
                raw_content="",
                display_text="Review action (1. confirm, 2. cancel)",
                resolved_skill={"skill": "review"},
                skill_output=None,
                workflow_pending=True,
            )

        async def answer_workflow(self, value: str) -> ChatResponse:
            prompts.append(value)
            if value == "docs":
                return ChatResponse(
                    raw_content="",
                    display_text="Choose responses must select a listed choice.\nReview action (1. confirm, 2. cancel)",
                    resolved_skill={"skill": "workflow"},
                    skill_output=None,
                    workflow_pending=True,
                )
            return ChatResponse(
                raw_content="",
                display_text="confirmed",
                resolved_skill={"skill": "workflow"},
                skill_output=None,
                workflow_pending=False,
            )

        async def close(self) -> None:
            pass

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())

    _run_inline(RuntimeState(cwd="/tmp"), "review this")

    assert prompts == ["docs", "confirm"]
    assert capsys.readouterr().out.splitlines() == [
        "Review action (1. confirm, 2. cancel)",
        "Choose responses must select a listed choice.",
        "Review action (1. confirm, 2. cancel)",
        "confirmed",
    ]


def test_run_inline_fails_cleanly_when_workflow_needs_non_tty_input(
    monkeypatch, capsys
):
    events: list[str] = []

    class FakeStdin:
        def isatty(self) -> bool:
            return False

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            pass

        async def send(self, prompt: str) -> ChatResponse:
            return ChatResponse(
                raw_content="",
                display_text="Schedule reminder? (1. confirm, 2. cancel)",
                resolved_skill={"skill": "reminders"},
                skill_output=None,
                workflow_pending=True,
            )

        async def cancel_workflow(self) -> ChatResponse:
            events.append("cancel")
            return ChatResponse(
                raw_content="",
                display_text="Workflow cancelled.",
                resolved_skill=None,
                skill_output=None,
                workflow_pending=False,
            )

        async def close(self) -> None:
            events.append("close")

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())

    with pytest.raises(SystemExit) as exit_info:
        _run_inline(RuntimeState(cwd="/tmp"), "remind me in one minute to call pablo")

    captured = capsys.readouterr()
    normalized_output = " ".join(captured.out.split())
    assert exit_info.value.code == 1
    assert events == ["cancel", "close"]
    assert (
        "Inline interaction requires a terminal. Use the TUI chat for non-interactive runs."
        in normalized_output
    )


def test_run_inline_cancels_workflow_on_eof(monkeypatch):
    events: list[str] = []

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return ""

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            pass

        async def send(self, prompt: str) -> ChatResponse:
            return ChatResponse(
                raw_content="",
                display_text="Name",
                resolved_skill={"skill": "asker"},
                skill_output=None,
                workflow_pending=True,
            )

        async def cancel_workflow(self) -> ChatResponse:
            events.append("cancel")
            return ChatResponse(
                raw_content="",
                display_text="Workflow cancelled.",
                resolved_skill=None,
                skill_output=None,
                workflow_pending=False,
            )

        async def close(self) -> None:
            events.append("close")

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())

    with pytest.raises(SystemExit) as exit_info:
        _run_inline(RuntimeState(cwd="/tmp"), "ask me something")

    assert exit_info.value.code == 130
    assert events == ["cancel", "close"]


def test_run_inline_cancels_workflow_on_keyboard_interrupt(monkeypatch):
    events: list[str] = []

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            raise KeyboardInterrupt

    class FakeEngine:
        def __init__(self, state, *, allow_script_interaction: bool = True):
            pass

        async def send(self, prompt: str) -> ChatResponse:
            return ChatResponse(
                raw_content="",
                display_text="Name",
                resolved_skill={"skill": "asker"},
                skill_output=None,
                workflow_pending=True,
            )

        async def cancel_workflow(self) -> ChatResponse:
            events.append("cancel")
            return ChatResponse(
                raw_content="",
                display_text="Workflow cancelled.",
                resolved_skill=None,
                skill_output=None,
                workflow_pending=False,
            )

        async def close(self) -> None:
            events.append("close")

    monkeypatch.setattr("dori.main.ConversationEngine", FakeEngine)
    monkeypatch.setattr("dori.main.sys.stdin", FakeStdin())

    with pytest.raises(SystemExit) as exit_info:
        _run_inline(RuntimeState(cwd="/tmp"), "ask me something")

    assert exit_info.value.code == 130
    assert events == ["cancel", "close"]
