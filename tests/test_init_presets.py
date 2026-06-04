import hashlib
import json
from pathlib import Path

from mnemo8.commands import _choose_reminders_backend, init_workspace, update_workspace

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
    assert (runtime_home / "DORI.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "DORI.md"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "assets" / "dori.png").read_bytes() == (
        ROOT / "boilerplate" / "assets" / "dori.png"
    ).read_bytes()
    assert (runtime_home / "scripts" / "reminders.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "template.py"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "skills" / "reminders.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "template.md"
    ).read_text(encoding="utf-8")
    manifest = json.loads((runtime_home / ".manifest.json").read_text(encoding="utf-8"))
    assert manifest["DORI.md"]
    assert manifest["assets/dori.png"]
    assert manifest["scripts/reminders.py"]
    assert manifest["skills/reminders.md"]


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


def test_update_workspace_replaces_unmodified_managed_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"

    init_workspace(str(ROOT), reminders_backend="template")

    target = runtime_home / "scripts" / "calendar.py"
    original = target.read_text(encoding="utf-8")

    target.write_text("old packaged content\n", encoding="utf-8")
    manifest_path = runtime_home / ".manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous_md5 = hashlib.md5(b"old packaged content\n").hexdigest()  # noqa: S324
    manifest["scripts/calendar.py"] = previous_md5
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    update_workspace(str(ROOT))

    assert target.read_text(encoding="utf-8") == original
    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest["scripts/calendar.py"] != previous_md5


def test_update_workspace_preserves_user_modified_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"

    init_workspace(str(ROOT), reminders_backend="template")

    target = runtime_home / "scripts" / "calendar.py"
    original = target.read_text(encoding="utf-8")
    target.write_text(f"{original}\n# local change\n", encoding="utf-8")

    update_workspace(str(ROOT))

    assert target.read_text(encoding="utf-8") == f"{original}\n# local change\n"
    assert "not updated because it has local modifications" in capsys.readouterr().out


def test_update_workspace_migrates_legacy_dori_persona_without_overwriting_changes(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    runtime_home.mkdir()

    legacy_content = "You are a custom legacy persona.\n"
    legacy_path = runtime_home / "AGENTS.md"
    legacy_path.write_text(legacy_content, encoding="utf-8")

    manifest_path = runtime_home / ".manifest.json"
    legacy_hash = hashlib.md5(b"old packaged content\n").hexdigest()  # noqa: S324
    manifest_path.write_text(
        json.dumps({"AGENTS.md": legacy_hash}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    update_workspace(str(ROOT))

    dori_path = runtime_home / "DORI.md"
    assert dori_path.read_text(encoding="utf-8") == legacy_content
    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest["DORI.md"] == legacy_hash
    assert "AGENTS.md" not in updated_manifest


def test_update_workspace_recreates_missing_and_new_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"

    init_workspace(str(ROOT), reminders_backend="template")

    deleted_file = runtime_home / "skills" / "calendar.md"
    deleted_file.unlink()

    new_src = ROOT / "boilerplate" / "scripts" / "temporary-update-test.py"
    new_src.write_text("print('new file')\n", encoding="utf-8")
    try:
        update_workspace(str(ROOT))
    finally:
        new_src.unlink()

    assert deleted_file.read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "skills" / "calendar.md"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "scripts" / "temporary-update-test.py").read_text(
        encoding="utf-8"
    ) == "print('new file')\n"


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
    manifest = json.loads((runtime_home / ".manifest.json").read_text(encoding="utf-8"))
    assert "scripts/reminders.py" not in manifest
    assert "skills/reminders.md" not in manifest


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
