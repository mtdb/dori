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
