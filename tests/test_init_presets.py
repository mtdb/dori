import hashlib
import json
import subprocess
from pathlib import Path

from dori.commands import (
    _choose_reminders_backend,
    _choose_search_backend,
    init_workspace,
    update_workspace,
)

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SOURCE_COMMIT = "1346dda"
LEGACY_SEARCH_PATHS = [
    "skills/search/_index.md",
    "skills/search/web.md",
    "skills/search/news.md",
    "scripts/news.py",
]


def git_show_legacy_file(relative: Path) -> str:
    result = subprocess.run(
        ["git", "show", f"{LEGACY_SOURCE_COMMIT}:{relative.as_posix()}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_choose_reminders_backend_uses_prompt_default_path():
    prompt_calls = []

    def fake_prompt(message, *, choices, default):
        prompt_calls.append((message, choices, default))
        return "dbus"

    assert _choose_reminders_backend(None, prompt=fake_prompt) == "dbus"
    assert prompt_calls == [
        ("Choose reminders backend", ["dbus", "template"], "template")
    ]


def test_choose_search_backend_uses_ddgs_default() -> None:
    prompt_calls = []

    def fake_prompt(message, *, choices, default):
        prompt_calls.append((message, choices, default))
        return "tavily"

    assert _choose_search_backend(None, prompt=fake_prompt) == "tavily"
    assert prompt_calls == [("Choose search backend", ["ddgs", "tavily"], "ddgs")]


def test_init_workspace_installs_template_reminders_preset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    init_workspace(str(ROOT), reminders_backend="template", search_backend="ddgs")

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
    assert (runtime_home / "scripts" / "web.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "ddgs.py"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "skills" / "web.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "ddgs.md"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "scripts" / "_web_common.py").read_text(
        encoding="utf-8"
    ) == (ROOT / "boilerplate" / "scripts" / "_web_common.py").read_text(
        encoding="utf-8"
    )
    manifest = json.loads((runtime_home / ".manifest.json").read_text(encoding="utf-8"))
    assert manifest["DORI.md"]
    assert manifest["assets/dori.png"]
    assert manifest["scripts/reminders.py"]
    assert manifest["skills/reminders.md"]
    assert manifest["scripts/web.py"]
    assert manifest["skills/web.md"]
    assert manifest["scripts/_web_common.py"]


def test_init_workspace_installs_dbus_reminders_preset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    init_workspace(str(ROOT), reminders_backend="dbus", search_backend="ddgs")

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


def test_init_workspace_installs_tavily_search_preset(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    init_workspace(str(ROOT), reminders_backend="template", search_backend="tavily")

    runtime_home = tmp_path / ".dori"
    assert (runtime_home / "scripts" / "web.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "tavily.py"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "skills" / "web.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "tavily.md"
    ).read_text(encoding="utf-8")


def test_update_workspace_replaces_unmodified_managed_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"

    init_workspace(str(ROOT), reminders_backend="template", search_backend="ddgs")

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

    init_workspace(str(ROOT), reminders_backend="template", search_backend="ddgs")

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

    init_workspace(str(ROOT), reminders_backend="template", search_backend="ddgs")

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

    init_workspace(str(ROOT), reminders_backend="dbus", search_backend="ddgs")

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

    init_workspace(str(ROOT), reminders_backend="dbus", search_backend="ddgs")

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

    init_workspace(str(ROOT), reminders_backend="dbus", search_backend="ddgs")


def test_init_workspace_preserves_existing_search_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    scripts_dir = runtime_home / "scripts"
    skills_dir = runtime_home / "skills"
    scripts_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    existing_script = scripts_dir / "web.py"
    existing_skill = skills_dir / "web.md"
    existing_script.write_text("print('custom search')\n", encoding="utf-8")
    existing_skill.write_text("# Custom web skill\n", encoding="utf-8")

    init_workspace(str(ROOT), reminders_backend="template", search_backend="tavily")

    assert existing_script.read_text(encoding="utf-8") == "print('custom search')\n"
    assert existing_skill.read_text(encoding="utf-8") == "# Custom web skill\n"
    manifest = json.loads((runtime_home / ".manifest.json").read_text(encoding="utf-8"))
    assert "scripts/web.py" not in manifest
    assert "skills/web.md" not in manifest


def test_init_workspace_installs_ddgs_skill_for_partial_existing_search_pair(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    scripts_dir = runtime_home / "scripts"
    skills_dir = runtime_home / "skills"
    scripts_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    existing_script = scripts_dir / "web.py"
    existing_script.write_text("print('custom search')\n", encoding="utf-8")

    init_workspace(str(ROOT), reminders_backend="template", search_backend="tavily")

    assert existing_script.read_text(encoding="utf-8") == "print('custom search')\n"
    assert (skills_dir / "web.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "ddgs.md"
    ).read_text(encoding="utf-8")


def test_init_workspace_installs_ddgs_script_for_partial_existing_search_pair(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    scripts_dir = runtime_home / "scripts"
    skills_dir = runtime_home / "skills"
    scripts_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    existing_skill = skills_dir / "web.md"
    existing_skill.write_text("# Custom web skill\n", encoding="utf-8")

    init_workspace(str(ROOT), reminders_backend="template", search_backend="tavily")

    assert (scripts_dir / "web.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "ddgs.py"
    ).read_text(encoding="utf-8")
    assert existing_skill.read_text(encoding="utf-8") == "# Custom web skill\n"


def test_update_workspace_keeps_installed_search_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    init_workspace(str(ROOT), reminders_backend="template", search_backend="tavily")

    update_workspace(str(ROOT))

    runtime_web = tmp_path / ".dori" / "scripts" / "web.py"
    assert runtime_web.read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "tavily.py"
    ).read_text(encoding="utf-8")


def test_update_workspace_switches_unmodified_search_backend(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    init_workspace(str(ROOT), reminders_backend="template", search_backend="ddgs")

    update_workspace(str(ROOT), search_backend="tavily")

    runtime_web = tmp_path / ".dori" / "scripts" / "web.py"
    assert runtime_web.read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "tavily.py"
    ).read_text(encoding="utf-8")
    assert (tmp_path / ".dori" / "skills" / "web.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "tavily.md"
    ).read_text(encoding="utf-8")


def test_update_does_not_partially_switch_modified_search_pair(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    init_workspace(str(ROOT), reminders_backend="template", search_backend="ddgs")
    runtime_home = tmp_path / ".dori"
    web_skill = runtime_home / "skills" / "web.md"
    original_script = (runtime_home / "scripts" / "web.py").read_text(encoding="utf-8")
    original_skill = web_skill.read_text(encoding="utf-8")
    web_skill.write_text(f"{original_skill}\ncustom instructions\n", encoding="utf-8")

    update_workspace(str(ROOT), search_backend="tavily")

    assert (runtime_home / "scripts" / "web.py").read_text(encoding="utf-8") == (
        original_script
    )
    assert web_skill.read_text(encoding="utf-8") == (
        f"{original_skill}\ncustom instructions\n"
    )
    assert "search backend not switched" in capsys.readouterr().out


def test_update_removes_unmodified_managed_legacy_search_files(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    (runtime_home / "skills" / "search").mkdir(parents=True)
    (runtime_home / "scripts").mkdir(parents=True)
    manifest = {}
    legacy_sources = {
        "skills/search/_index.md": Path("boilerplate/skills/search/_index.md"),
        "skills/search/web.md": Path("boilerplate/skills/search/web.md"),
        "skills/search/news.md": Path("boilerplate/skills/search/news.md"),
        "scripts/news.py": Path("boilerplate/scripts/news.py"),
        "scripts/web.py": Path("boilerplate/scripts/web.py"),
    }
    for relative, source in legacy_sources.items():
        destination = runtime_home / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = git_show_legacy_file(source)
        destination.write_text(content, encoding="utf-8")
        manifest[relative] = hashlib.md5(content.encode("utf-8")).hexdigest()  # noqa: S324
    (runtime_home / ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    update_workspace(str(ROOT), search_backend="ddgs")

    for relative in LEGACY_SEARCH_PATHS:
        assert not (runtime_home / relative).exists()
    assert (runtime_home / "scripts" / "web.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "ddgs.py"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "skills" / "web.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "ddgs.md"
    ).read_text(encoding="utf-8")


def test_update_preserves_modified_legacy_search_file(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    scripts_dir = runtime_home / "scripts"
    legacy = runtime_home / "skills" / "search" / "news.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("# custom news skill\n", encoding="utf-8")
    (runtime_home / ".manifest.json").write_text(
        json.dumps(
            {
                "skills/search/news.md": hashlib.md5(
                    b"old packaged content\n"
                ).hexdigest()
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    update_workspace(str(ROOT), search_backend="ddgs")

    assert legacy.read_text(encoding="utf-8") == "# custom news skill\n"
    assert "local modifications" in capsys.readouterr().out

    assert (scripts_dir / "reminders.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "reminders" / "template.py"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "scripts" / "web.py").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "ddgs.py"
    ).read_text(encoding="utf-8")
    assert (runtime_home / "skills" / "web.md").read_text(encoding="utf-8") == (
        ROOT / "boilerplate" / "presets" / "search" / "ddgs.md"
    ).read_text(encoding="utf-8")
