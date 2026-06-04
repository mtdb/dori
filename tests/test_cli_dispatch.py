import sys
from types import SimpleNamespace

import pytest

from mnemo8.main import run, run_cli_skill


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

    monkeypatch.setattr("mnemo8.main.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["dori", "commit"])

    with pytest.raises(SystemExit) as exit_info:
        run()

    assert exit_info.value.code == 0
    assert capfd.readouterr().out.strip() == "commit from cli=True"


def test_cli_dispatch_reports_missing_skill_script(tmp_path, monkeypatch, capsys):
    (tmp_path / "scripts").mkdir()
    monkeypatch.setattr("mnemo8.main.get_runtime_home", lambda: tmp_path)
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
    monkeypatch.setattr("mnemo8.main.get_runtime_home", lambda: tmp_path)
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

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("mnemo8.main.get_runtime_home", lambda: tmp_path)
    monkeypatch.setattr("mnemo8.main.subprocess.run", fake_run)

    assert run_cli_skill("commit", [], str(tmp_path)) == 0

    _, kwargs = calls[0]
    assert "capture_output" not in kwargs
    assert "text" not in kwargs


def test_cli_dispatches_update_command(monkeypatch):
    called = []

    def fake_update_workspace(cwd):
        called.append(cwd)

    monkeypatch.setattr("mnemo8.main.update_workspace", fake_update_workspace)
    monkeypatch.setattr("mnemo8.main.os.getcwd", lambda: "/tmp/dori-project")
    monkeypatch.setattr(sys, "argv", ["dori", "update"])

    run()

    assert called == ["/tmp/dori-project"]
