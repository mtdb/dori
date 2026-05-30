import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIT_SCRIPT = ROOT / "boilerplate" / "scripts" / "git.py"


def load_git_script():
    spec = importlib.util.spec_from_file_location("dori_git_script", GIT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_normalize_topic_maps_common_phrasings_to_git_commands():
    git_script = load_git_script()

    cases = {
        "how do I squash the last three commits": "rebase",
        "delete a remote branch": "branch",
        "what is git cherry pick": "cherry-pick",
        "undo a commit safely": "revert",
        "show changes before committing": "diff",
        "move work to another branch with stash": "stash",
    }

    for raw_topic, expected in cases.items():
        assert git_script.normalize_topic(raw_topic) == expected


def test_normalize_topic_returns_none_for_unknown_topics():
    git_script = load_git_script()

    assert git_script.normalize_topic("configure my editor theme") is None
