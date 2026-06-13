import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMIT_SCRIPT = ROOT / "boilerplate" / "scripts" / "commit.py"


def load_commit_script():
    sys.path.insert(0, str(COMMIT_SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("dori_commit_script", COMMIT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_commit_script_prints_cancelled_on_interaction_cancelled(monkeypatch, capsys):
    commit_script = load_commit_script()
    cancelled_error = type("InteractionCancelled", (Exception,), {})

    monkeypatch.setattr(commit_script, "InteractionCancelled", cancelled_error)
    monkeypatch.setattr(
        commit_script,
        "run_interactive",
        lambda: (_ for _ in ()).throw(cancelled_error()),
    )
    monkeypatch.setattr(sys, "argv", ["commit.py", "{}"])

    with pytest.raises(SystemExit) as exit_info:
        commit_script.main()

    assert exit_info.value.code == 130
    assert capsys.readouterr().err.strip() == "Cancelled."
