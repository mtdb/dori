from types import SimpleNamespace

from mnemo8.commit_workflow import (
    ChangedFile,
    CommitGroup,
    amend_qualifies,
    build_commit_message,
    build_commit_message_prompt,
    commit_group,
    detect_scope,
    detect_type,
    group_files,
    parse_status_lines,
)


def test_parse_status_lines_handles_common_statuses():
    files = parse_status_lines(
        [
            " M mnemo8/chat.py",
            "?? mnemo8/commit_workflow.py",
            " D old.py",
            "R  before.py -> after.py",
        ]
    )

    assert [
        (file.path, file.status, file.old_path, file.index_status, file.worktree_status)
        for file in files
    ] == [
        ("mnemo8/chat.py", "modified", None, " ", "M"),
        ("mnemo8/commit_workflow.py", "new", None, "?", "?"),
        ("old.py", "deleted", None, " ", "D"),
        ("after.py", "renamed", "before.py", "R", " "),
    ]


def test_group_files_groups_source_and_tests_by_module():
    files = [
        ChangedFile("mnemo8/chat.py", "modified"),
        ChangedFile("tests/test_chat.py", "modified"),
        ChangedFile("README.md", "modified"),
    ]

    groups = group_files(files)

    assert [[file.path for file in group] for group in groups] == [
        ["mnemo8/chat.py", "tests/test_chat.py"],
        ["README.md"],
    ]


def test_detect_type_for_docs_tests_build_and_new_files():
    assert detect_type([ChangedFile("README.md", "modified")]) == "docs"
    assert detect_type([ChangedFile("tests/test_chat.py", "modified")]) == "test"
    assert detect_type([ChangedFile("pyproject.toml", "modified")]) == "build"
    assert detect_type([ChangedFile("mnemo8/new_feature.py", "new")]) == "feat"


def test_detect_scope_prefers_shared_meaningful_directory():
    files = [
        ChangedFile("mnemo8/chat.py", "modified"),
        ChangedFile("mnemo8/schemas.py", "modified"),
    ]

    assert detect_scope(files) == "mnemo8"


def test_amend_qualifies_only_for_matching_unpushed_type_and_scope():
    assert amend_qualifies("fix(tui): 🐛 update input", "fix", "tui", pushed=False)
    assert not amend_qualifies("fix(tui): 🐛 update input", "feat", "tui", pushed=False)
    assert not amend_qualifies("fix(tui): 🐛 update input", "fix", "chat", pushed=False)
    assert not amend_qualifies("fix(tui): 🐛 update input", "fix", "tui", pushed=True)


def test_build_commit_message_uses_conventional_commit_with_body_for_multiple_files():
    group = CommitGroup(
        files=[
            ChangedFile("mnemo8/chat.py", "modified"),
            ChangedFile("tests/test_chat.py", "modified"),
        ],
        commit_type="fix",
        scope="chat",
        emoji="🐛",
    )

    assert build_commit_message(group) == (
        "fix(chat): 🐛 update chat\n\n"
        "🔧 update mnemo8/chat.py\n"
        "✅ update tests/test_chat.py"
    )


def test_build_commit_message_prompt_includes_group_context():
    group = CommitGroup(
        files=[
            ChangedFile(
                "mnemo8/commit_workflow.py",
                "modified",
                diff="+def suggest_commit_message(group):\n+    return generated",
            ),
            ChangedFile(
                "tests/test_commit_workflow.py",
                "modified",
                diff="+def test_suggest_commit_message():\n+    assert message",
            ),
        ],
        commit_type="fix",
        scope="commit",
        emoji="🐛",
    )

    messages = build_commit_message_prompt(group)

    assert messages[0]["role"] == "system"
    assert "output only the commit message" in messages[0]["content"].lower()
    user_prompt = messages[1]["content"]
    assert "Detected type: fix" in user_prompt
    assert "Detected scope: commit" in user_prompt
    assert "modified mnemo8/commit_workflow.py" in user_prompt
    assert "modified tests/test_commit_workflow.py" in user_prompt
    assert "suggest_commit_message" in user_prompt
    assert "test_suggest_commit_message" in user_prompt


def test_commit_group_stages_selected_files_and_commits(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, cwd, check):
        calls.append(cmd)
        if cmd[:2] == ["git", "commit"]:
            return SimpleNamespace(returncode=0, stdout="[main abc123] ok", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("mnemo8.commit_workflow.subprocess.run", fake_run)
    group = CommitGroup(
        files=[ChangedFile("mnemo8/chat.py", "modified")],
        message="fix(chat): 🐛 update chat",
    )

    sha, output = commit_group(group, "/repo")

    assert sha == "abc123"
    assert "[main abc123] ok" in output
    assert calls[0] == ["git", "add", "-A", "--", "mnemo8/chat.py"]
    assert calls[1] == ["git", "commit", "-m", "fix(chat): 🐛 update chat"]


def test_commit_group_retries_hook_failure_with_same_group_only(monkeypatch):
    calls: list[list[str]] = []
    commit_attempts = 0

    def fake_run(cmd, capture_output, text, cwd, check):
        nonlocal commit_attempts
        calls.append(cmd)
        if cmd[:2] == ["git", "commit"]:
            commit_attempts += 1
            if commit_attempts == 1:
                return SimpleNamespace(returncode=1, stdout="", stderr="hook failed")
            return SimpleNamespace(returncode=0, stdout="[main abc123] ok", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("mnemo8.commit_workflow.subprocess.run", fake_run)
    group = CommitGroup(
        files=[ChangedFile("mnemo8/chat.py", "modified")],
        message="fix(chat): 🐛 update chat",
    )

    sha, output = commit_group(group, "/repo")

    assert sha == "abc123"
    assert "hook failed" in output
    assert calls == [
        ["git", "add", "-A", "--", "mnemo8/chat.py"],
        ["git", "commit", "-m", "fix(chat): 🐛 update chat"],
        ["git", "add", "-A", "--", "mnemo8/chat.py"],
        ["git", "commit", "-m", "fix(chat): 🐛 update chat"],
        ["git", "rev-parse", "--short", "HEAD"],
    ]


def test_commit_group_returns_git_add_error_without_traceback(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, cwd, check):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=128, stdout="", stderr="fatal: pathspec failed"
        )

    monkeypatch.setattr("mnemo8.commit_workflow.subprocess.run", fake_run)
    group = CommitGroup(
        files=[ChangedFile("missing.py", "deleted")],
        message="refactor: ♻️ remove missing",
    )

    sha, output = commit_group(group, "/repo")

    assert sha is None
    assert output == "fatal: pathspec failed"
    assert calls == [["git", "add", "-u", "--", "missing.py"]]


def test_commit_group_does_not_restage_already_staged_deletion(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, cwd, check):
        calls.append(cmd)
        if cmd[:2] == ["git", "commit"]:
            return SimpleNamespace(returncode=0, stdout="[main abc123] ok", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("mnemo8.commit_workflow.subprocess.run", fake_run)
    group = CommitGroup(
        files=[
            ChangedFile(
                "static/scripts/jquery-1.7.2.min.js",
                "deleted",
                index_status="D",
                worktree_status=" ",
            )
        ],
        message="refactor(static): ♻️ refactor static",
    )

    sha, output = commit_group(group, "/repo")

    assert sha == "abc123"
    assert "[main abc123] ok" in output
    assert calls == [
        ["git", "commit", "-m", "refactor(static): ♻️ refactor static"],
        ["git", "rev-parse", "--short", "HEAD"],
    ]
