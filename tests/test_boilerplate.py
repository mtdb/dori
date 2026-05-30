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
