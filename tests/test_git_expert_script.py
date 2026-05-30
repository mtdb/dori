import importlib.util
from pathlib import Path
from types import SimpleNamespace

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


def test_normalize_topic_prefers_stable_topic_for_multi_command_phrasing():
    git_script = load_git_script()

    assert git_script.normalize_topic("switch branch") == "branch"


def test_retrieve_local_docs_uses_only_read_only_help_commands(monkeypatch):
    git_script = load_git_script()
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, timeout, check):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=0,
            stdout="usage: git rebase [options]\nReplay commits on top of another base tip.",
            stderr="",
        )

    monkeypatch.setattr(git_script.subprocess, "run", fake_run)

    docs = git_script.retrieve_local_docs("rebase")

    assert "Replay commits" in docs
    assert calls == [["git", "help", "rebase"]]


def test_retrieve_local_docs_falls_back_to_short_help_then_man(monkeypatch):
    git_script = load_git_script()
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, timeout, check):
        calls.append(cmd)
        if cmd == ["git", "help", "stash"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="missing")
        if cmd == ["git", "stash", "-h"]:
            return SimpleNamespace(
                returncode=129, stdout="usage: git stash list", stderr=""
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(git_script.subprocess, "run", fake_run)

    docs = git_script.retrieve_local_docs("stash")

    assert docs == "usage: git stash list"
    assert calls == [["git", "help", "stash"], ["git", "stash", "-h"]]


def test_retrieve_local_docs_falls_back_to_man_when_git_help_fails(monkeypatch):
    git_script = load_git_script()
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, timeout, check):
        calls.append(cmd)
        if cmd == ["git", "help", "tag"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="missing")
        if cmd == ["git", "tag", "-h"]:
            return SimpleNamespace(returncode=129, stdout="", stderr="usage")
        if cmd == ["man", "git-tag"]:
            return SimpleNamespace(returncode=0, stdout="GIT-TAG(1)", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(git_script.subprocess, "run", fake_run)

    docs = git_script.retrieve_local_docs("tag")

    assert docs == "GIT-TAG(1)"
    assert calls == [
        ["git", "help", "tag"],
        ["git", "tag", "-h"],
        ["man", "git-tag"],
    ]


def test_retrieve_local_docs_returns_none_when_docs_are_missing(monkeypatch):
    git_script = load_git_script()

    def fake_run(cmd, capture_output, text, timeout, check):
        return SimpleNamespace(returncode=1, stdout="", stderr="missing")

    monkeypatch.setattr(git_script.subprocess, "run", fake_run)

    assert git_script.retrieve_local_docs("restore") is None


def test_build_expert_prompt_is_english_only_and_evidence_scoped():
    git_script = load_git_script()

    messages = git_script.build_expert_messages(
        topic="rebase",
        raw_text="How do I squash commits?",
        context="last three commits",
        docs="usage: git rebase [options]",
    )

    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "read-only Git expert" in system_prompt
    assert (
        "Answer only from the provided local Git documentation fragments"
        in system_prompt
    )
    assert "Do not invent commands" in system_prompt
    assert "Untrusted user question:" in user_prompt
    assert "Untrusted user-provided context:" in user_prompt
    assert "--- LOCAL GIT DOCUMENTATION START ---" in user_prompt
    assert "--- LOCAL GIT DOCUMENTATION END ---" in user_prompt
    assert "last three commits" in user_prompt
    assert "usage: git rebase" in user_prompt


def test_generate_answer_returns_model_content(monkeypatch):
    git_script = load_git_script()

    def fake_chat(model, messages, options):
        return {
            "message": {
                "content": (
                    "🌿 [Git - rebase]\n"
                    "Summary: Rebase replays commits.\n"
                    "Steps:\n"
                    "1. Run git rebase."
                )
            }
        }

    monkeypatch.setattr(git_script.ollama, "chat", fake_chat)

    answer = git_script.generate_answer(
        topic="rebase",
        raw_text="How do I rebase?",
        context=None,
        docs="usage: git rebase [options]",
    )

    assert answer.startswith("🌿 [Git - rebase]")


def test_generate_answer_abstains_on_empty_or_unsafe_model_output(monkeypatch):
    git_script = load_git_script()
    responses = iter(
        [
            "",
            "Summary: Rebase replays commits.\nSteps:\n1. Run git rebase.",
            "🌿 [Git - rebase]\nRun git reset --hard",
        ]
    )

    def fake_chat(model, messages, options):
        return {"message": {"content": next(responses)}}

    monkeypatch.setattr(git_script.ollama, "chat", fake_chat)

    assert (
        git_script.generate_answer(
            topic="rebase",
            raw_text="How do I rebase?",
            context=None,
            docs="usage: git rebase [options]",
        )
        == git_script.ABSTENTION_MESSAGE
    )
    assert (
        git_script.generate_answer(
            topic="rebase",
            raw_text="How do I rebase?",
            context=None,
            docs="usage: git rebase [options]",
        )
        == git_script.ABSTENTION_MESSAGE
    )
    assert (
        git_script.generate_answer(
            topic="rebase",
            raw_text="How do I rebase?",
            context=None,
            docs="usage: git rebase [options]",
        )
        == git_script.ABSTENTION_MESSAGE
    )


def test_answer_payload_abstains_when_topic_is_unknown():
    git_script = load_git_script()

    payload = {
        "skill": "git",
        "confidence": 0.95,
        "topic": "configure my editor theme",
        "raw_text": "How do I configure my editor theme?",
    }

    assert git_script.answer_payload(payload) == git_script.ABSTENTION_MESSAGE


def test_answer_payload_uses_raw_text_when_topic_is_missing(monkeypatch):
    git_script = load_git_script()

    monkeypatch.setattr(
        git_script, "retrieve_local_docs", lambda command: "usage: git diff"
    )
    monkeypatch.setattr(
        git_script,
        "generate_answer",
        lambda topic, raw_text, context, docs: f"🌿 [Git - {topic}]\nSummary: ok",
    )

    payload = {
        "skill": "git",
        "confidence": 0.95,
        "raw_text": "How do I show changes before committing?",
    }

    assert git_script.answer_payload(payload).startswith("🌿 [Git - diff]")


def test_main_prints_abstention_for_invalid_json(capsys, monkeypatch):
    git_script = load_git_script()

    monkeypatch.setattr("sys.argv", ["git.py", "{not-json"])

    git_script.main()

    assert capsys.readouterr().out.strip() == git_script.ABSTENTION_MESSAGE
