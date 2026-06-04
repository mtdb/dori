from dori.loader import load_agents


def test_load_agents_reads_dori_md(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime_home = tmp_path / ".dori"
    runtime_home.mkdir()
    (runtime_home / "DORI.md").write_text("You are Dori.\n", encoding="utf-8")

    assert load_agents() == "You are Dori.\n"
