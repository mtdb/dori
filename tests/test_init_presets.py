from pathlib import Path

from mnemo8.commands import _choose_reminders_backend, init_workspace

ROOT = Path(__file__).resolve().parents[1]


def test_choose_reminders_backend_uses_prompt_default_path():
    prompt_calls = []

    def fake_prompt(message, *, choices, default):
        prompt_calls.append((message, choices, default))
        return "dbus"

    assert _choose_reminders_backend(None, prompt=fake_prompt) == "dbus"
    assert prompt_calls == [
        ("Choose reminders backend", ["dbus", "template"], "template")
    ]


def test_init_workspace_installs_template_reminders_preset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    init_workspace(str(ROOT), reminders_backend="template")

    runtime_home = tmp_path / ".dori"
    assert (runtime_home / "assets" / "dori.png").read_bytes() == (
        ROOT / "boilerplate" / "assets" / "dori.png"
    ).read_bytes()
    assert (runtime_home / "scripts" / "reminders.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "template.py"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "skills" / "reminders.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "template.md"
    ).read_text(encoding="utf-8")


def test_init_workspace_installs_dbus_reminders_preset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    init_workspace(str(ROOT), reminders_backend="dbus")

    runtime_home = tmp_path / ".dori"
    assert (runtime_home / "assets" / "dori.png").read_bytes() == (
        ROOT / "boilerplate" / "assets" / "dori.png"
    ).read_bytes()
    assert (runtime_home / "scripts" / "reminders.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "dbus.py"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "skills" / "reminders.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "dbus.md"
    ).read_text(encoding="utf-8")


def test_init_workspace_preserves_existing_reminders_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    scripts_dir = runtime_home / "scripts"
    skills_dir = runtime_home / "skills"
    scripts_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    existing_script = scripts_dir / "reminders.py"
    existing_skill = skills_dir / "reminders.md"
    existing_script.write_text("print('custom script')\n", encoding="utf-8")
    existing_skill.write_text("# Custom reminders skill\n", encoding="utf-8")

    init_workspace(str(ROOT), reminders_backend="dbus")

    assert existing_script.read_text(encoding="utf-8") == "print('custom script')\n"
    assert existing_skill.read_text(encoding="utf-8") == "# Custom reminders skill\n"


def test_init_workspace_installs_template_skill_for_partial_existing_reminders_even_with_dbus(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    scripts_dir = runtime_home / "scripts"
    skills_dir = runtime_home / "skills"
    scripts_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    existing_script = scripts_dir / "reminders.py"
    existing_script.write_text("print('custom script')\n", encoding="utf-8")

    init_workspace(str(ROOT), reminders_backend="dbus")

    assert existing_script.read_text(encoding="utf-8") == "print('custom script')\n"
    assert (skills_dir / "reminders.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "template.md"
    ).read_text(encoding="utf-8")


def test_init_workspace_installs_template_script_for_partial_existing_reminders_even_with_dbus(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    scripts_dir = runtime_home / "scripts"
    skills_dir = runtime_home / "skills"
    scripts_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    existing_skill = skills_dir / "reminders.md"
    existing_skill.write_text("# Custom reminders skill\n", encoding="utf-8")

    init_workspace(str(ROOT), reminders_backend="dbus")

    assert (scripts_dir / "reminders.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "template.py"
    ).read_text(encoding="utf-8")
    assert existing_skill.read_text(encoding="utf-8") == "# Custom reminders skill\n"
