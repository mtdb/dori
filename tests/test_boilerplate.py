import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from dori.schemas import validate_skill_payload

ROOT = Path(__file__).resolve().parents[1]


def test_packaged_commit_workflow_matches_source_boilerplate() -> None:
    source = ROOT / "boilerplate" / "scripts" / "_commit_workflow.py"
    packaged = ROOT / "dori" / "boilerplate" / "scripts" / "_commit_workflow.py"

    assert packaged.read_bytes() == source.read_bytes()


def load_reminders_dbus_module() -> ModuleType:
    path = ROOT / "boilerplate" / "presets" / "reminders" / "dbus.py"
    spec = importlib.util.spec_from_file_location("reminders_dbus", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_search_boilerplate_uses_provider_presets() -> None:
    presets_dir = ROOT / "boilerplate" / "presets" / "search"

    assert sorted(path.name for path in presets_dir.iterdir() if path.is_file()) == [
        "ddgs.md",
        "ddgs.py",
        "tavily.md",
        "tavily.py",
    ]
    assert not (ROOT / "boilerplate" / "skills" / "search").exists()
    assert not (ROOT / "boilerplate" / "scripts" / "web.py").exists()
    assert not (ROOT / "boilerplate" / "scripts" / "news.py").exists()


def test_web_payload_accepts_supported_freshness() -> None:
    payload = {
        "skill": "web",
        "confidence": 0.95,
        "query": "Nintendo Switch 2 release date",
        "freshness": "month",
        "raw_text": "When was the Nintendo Switch 2 released?",
    }

    normalized, error = validate_skill_payload(payload)

    assert error is None
    assert normalized is not None
    assert normalized["freshness"] == "month"


def test_web_payload_rejects_unsupported_freshness() -> None:
    payload = {
        "skill": "web",
        "confidence": 0.95,
        "query": "Spain population",
        "freshness": "hour",
        "raw_text": "What is Spain's population right now?",
    }

    normalized, error = validate_skill_payload(payload)

    assert normalized is None
    assert error == "I need you to rephrase or restate: freshness."


def test_news_payload_is_no_longer_registered() -> None:
    payload = {
        "skill": "news",
        "confidence": 0.95,
        "raw_text": "latest console news",
    }

    normalized, error = validate_skill_payload(payload)

    assert error is None
    assert normalized == payload


def test_git_skill_is_read_only_expert_skill() -> None:
    git_skill = ROOT / "boilerplate" / "skills" / "devtools" / "git.md"
    content = git_skill.read_text(encoding="utf-8")

    assert "# Git Expert Skill" in content
    assert "informational question" in content
    assert "read-only question" not in content
    assert "read-only" in content
    assert "local Git documentation" in content
    assert "I could not find enough local documentation to answer safely" in content
    assert "Do not inspect the repository" in content
    assert "Do not run repository-mutating commands" in content
    assert (
        "Write answers in English even when the user asks in another language"
        in content
    )


def test_git_skill_examples_include_required_payload_fields() -> None:
    git_skill = ROOT / "boilerplate" / "skills" / "devtools" / "git.md"
    content = git_skill.read_text(encoding="utf-8")
    assistant_lines = [
        line for line in content.splitlines() if line.startswith("Assistant: ")
    ]

    assert assistant_lines
    assert "reset vs revert" not in content
    assert 'topic": "revert"' in content

    for line in assistant_lines:
        assert '"skill": "git"' in line
        assert '"confidence":' in line
        assert '"topic":' in line
        assert '"raw_text":' in line


def test_boilerplate_skill_examples_include_confidence_and_raw_text() -> None:
    skill_files = [
        path
        for skill_dir in [
            ROOT / "boilerplate" / "skills",
            ROOT / "boilerplate" / "presets" / "reminders",
            ROOT / "boilerplate" / "presets" / "search",
        ]
        for path in skill_dir.rglob("*.md")
        if path.name != "_index.md"
    ]

    assert skill_files

    for skill_file in skill_files:
        content = skill_file.read_text(encoding="utf-8")
        assistant_lines = [
            line.removeprefix("Assistant: ")
            for line in content.splitlines()
            if line.startswith("Assistant: ")
        ]

        assert assistant_lines, f"{skill_file} should include at least one example"

        for line in assistant_lines:
            payload = json.loads(line)
            assert payload["skill"]
            assert 0.0 <= payload["confidence"] <= 1.0
            assert payload["raw_text"]


def test_non_expert_boilerplate_scripts_write_errors_to_stderr() -> None:
    script_names = [
        "analyze-folder.py",
        "calendar.py",
        "docker.py",
    ]

    for script_name in script_names:
        result = subprocess.run(
            [sys.executable, str(ROOT / "boilerplate" / "scripts" / script_name)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1
        assert result.stdout == ""
        assert "Error: Missing JSON payload" in result.stderr


def test_reminders_presets_include_template_and_dbus() -> None:
    presets_dir = ROOT / "boilerplate" / "presets" / "reminders"

    assert sorted(path.name for path in presets_dir.iterdir() if path.is_file()) == [
        "dbus.md",
        "dbus.py",
        "template.md",
        "template.py",
    ]
    assert (ROOT / "boilerplate" / "DORI.md").exists()
    assert not (ROOT / "boilerplate" / "scripts" / "reminders.py").exists()
    assert not (ROOT / "boilerplate" / "skills" / "reminders.md").exists()


def test_reminders_template_preset_writes_errors_to_stderr() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "boilerplate" / "presets" / "reminders" / "template.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Error: Missing JSON payload" in result.stderr


def test_reminders_dbus_preset_rejects_unsupported_time() -> None:
    payload = {
        "skill": "reminders",
        "confidence": 0.95,
        "message": "drink water",
        "when": "tomorrow at 9am",
        "raw_text": "Remind me to drink water tomorrow at 9am",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "boilerplate" / "presets" / "reminders" / "dbus.py"),
            json.dumps(payload),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Use a relative time like 'in 20 minutes'" in result.stderr


def test_reminders_dbus_preset_supports_dry_run_relative_time() -> None:
    payload = {
        "skill": "reminders",
        "confidence": 0.95,
        "message": "drink water",
        "when": "in 20 minutes",
        "raw_text": "Remind me to drink water in 20 minutes",
        "dry_run": True,
    }
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "boilerplate" / "presets" / "reminders" / "dbus.py"),
            json.dumps(payload),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert (
        "[D-Bus]: Scheduled reminder for 'drink water' in 20 minutes." in result.stdout
    )


def test_reminders_dbus_preset_builds_notify_send_command_with_project_icon() -> None:
    dbus = load_reminders_dbus_module()
    command = dbus._notify_send_command("drink water")

    assert command[:3] == [
        "notify-send",
        "-i",
        str(ROOT / "boilerplate" / "assets" / "dori.png"),
    ]
    assert command[3:] == ["Dori reminder", "drink water"]


def test_reminders_dbus_preset_schedules_detached_python_child(monkeypatch) -> None:
    dbus = load_reminders_dbus_module()
    payload = {
        "skill": "reminders",
        "confidence": 0.95,
        "message": 'drink "water"; rm -rf /',
        "when": "in 30 seconds",
        "raw_text": 'Remind me to drink "water"; rm -rf / in 30 seconds',
    }
    which_calls = []
    popen_calls = []

    def fake_which(command: str) -> str:
        which_calls.append(command)
        return "/usr/bin/notify-send"

    def fake_popen(args, **kwargs):
        popen_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(dbus.shutil, "which", fake_which)
    monkeypatch.setattr(dbus.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        dbus.sys,
        "argv",
        [
            str(ROOT / "boilerplate" / "presets" / "reminders" / "dbus.py"),
            json.dumps(payload),
        ],
    )

    dbus.main()

    assert which_calls == ["notify-send"]
    assert len(popen_calls) == 1
    args, kwargs = popen_calls[0]
    assert args[:2] == [sys.executable, "-c"]
    assert args[-3:] == [
        "30",
        'drink "water"; rm -rf /',
        str(ROOT / "boilerplate" / "assets" / "dori.png"),
    ]
    assert kwargs == {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }


def test_reminders_dbus_preset_requires_notify_send(monkeypatch, capsys) -> None:
    dbus = load_reminders_dbus_module()
    payload = {
        "skill": "reminders",
        "confidence": 0.95,
        "message": "drink water",
        "when": "in 30 seconds",
        "raw_text": "Remind me to drink water in 30 seconds",
    }

    monkeypatch.setattr(dbus.shutil, "which", lambda command: None)
    monkeypatch.setattr(
        dbus.sys,
        "argv",
        [
            str(ROOT / "boilerplate" / "presets" / "reminders" / "dbus.py"),
            json.dumps(payload),
        ],
    )

    try:
        dbus.main()
    except SystemExit as error:
        assert error.code == 1
    else:
        raise AssertionError("Expected SystemExit(1)")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error: D-Bus reminders require notify-send to be installed." in captured.err


def test_docs_describe_top_level_web_search_presets() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    how_it_works = (ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8")
    skill_guide = (ROOT / "docs" / "how-to-create-boilerplate-skills.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([readme, how_it_works, skill_guide])

    assert "Choose search backend" in combined
    assert "TAVILY_API_KEY" in combined
    assert "DORI_WEB_MODEL" in combined
    assert "DDGS" in combined
    assert "skills/search/news.md" not in combined
    assert "**Experts available**: web, news" not in combined


def test_analyze_folder_script_summarizes_project_metadata(tmp_path: Path) -> None:
    project = tmp_path / "sample-app"
    project.mkdir()
    (project / "README.md").write_text(
        "# Sample App\n\nA tiny service for testing folder analysis.\n",
        encoding="utf-8",
    )
    (project / "pyproject.toml").write_text(
        "[project]\n"
        'name = "sample-app"\n'
        'description = "Sample app from package metadata"\n',
        encoding="utf-8",
    )
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (project / "Procfile").write_text("web: python main.py\n", encoding="utf-8")

    payload = {
        "skill": "analyze-folder",
        "confidence": 0.95,
        "path": str(project),
        "raw_text": "analyze this directory",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "boilerplate" / "scripts" / "analyze-folder.py"),
            json.dumps(payload),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "[Folder Analysis]" in result.stdout
    assert "Project: Sample App" in result.stdout
    assert "What it does: Sample app from package metadata" in result.stdout
    assert "pyproject.toml: Python project metadata" in result.stdout
    assert "main.py" in result.stdout
    assert "no extension: 1" in result.stdout
    assert "[no extension]" not in result.stdout
