import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_search_boilerplate_only_includes_web_and_news() -> None:
    skills_dir = ROOT / "boilerplate" / "skills" / "search"
    scripts_dir = ROOT / "boilerplate" / "scripts"

    assert sorted(path.stem for path in skills_dir.glob("*.md")) == [
        "_index",
        "news",
        "web",
    ]
    assert "**Experts available**: web, news" in (skills_dir / "_index.md").read_text(
        encoding="utf-8"
    )

    for removed_skill in ("images", "maps", "code"):
        assert not (skills_dir / f"{removed_skill}.md").exists()
        assert not (scripts_dir / f"{removed_skill}.py").exists()


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
        for path in (ROOT / "boilerplate" / "skills").rglob("*.md")
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
        "calendar.py",
        "commit.py",
        "docker.py",
        "news.py",
        "reminders.py",
        "web.py",
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
