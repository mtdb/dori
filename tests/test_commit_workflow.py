import importlib.util
import subprocess
import sys
from pathlib import Path

from rich.console import Console

ROOT = Path(__file__).resolve().parents[1]
COMMIT_WORKFLOW = ROOT / "boilerplate" / "scripts" / "_commit_workflow.py"

spec = importlib.util.spec_from_file_location("dori_commit_workflow", COMMIT_WORKFLOW)
assert spec is not None
assert spec.loader is not None
commit_workflow = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = commit_workflow
spec.loader.exec_module(commit_workflow)

ChangedFile = commit_workflow.ChangedFile
CommitRequest = commit_workflow.CommitRequest
StagedChanges = commit_workflow.StagedChanges
build_commit_message_prompt = commit_workflow.build_commit_message_prompt
fallback_commit_message = commit_workflow.fallback_commit_message
parse_status_lines = commit_workflow.parse_status_lines
resolve_forced_scope = commit_workflow.resolve_forced_scope
resolve_forced_type = commit_workflow.resolve_forced_type
resolve_mode = commit_workflow.resolve_mode
run_workflow = commit_workflow.run_workflow
staged_files = commit_workflow.staged_files
suggest_commit_message = commit_workflow.suggest_commit_message
truncate_diff = commit_workflow.truncate_diff
validate_commit_message = commit_workflow.validate_commit_message


def _request(**kwargs) -> CommitRequest:
    changes = kwargs.pop(
        "changes",
        StagedChanges(
            files=[ChangedFile("src/app.py", "modified")],
            stat=" src/app.py | 2 +-",
            diff="diff --git a/src/app.py b/src/app.py\n+print('hi')",
        ),
    )
    return CommitRequest(changes=changes, **kwargs)


def test_parse_status_lines_handles_common_statuses():
    files = parse_status_lines(
        [
            " M dori/chat.py",
            "?? dori/new_module.py",
            " D old.py",
            "R  before.py -> after.py",
        ]
    )

    assert [(file.path, file.status, file.old_path) for file in files] == [
        ("dori/chat.py", "modified", None),
        ("dori/new_module.py", "new", None),
        ("old.py", "deleted", None),
        ("after.py", "renamed", "before.py"),
    ]


def test_resolve_mode_prefers_cli_args():
    assert resolve_mode({"args": ["--partial"]}) == "partial"
    assert resolve_mode({"args": ["--full"]}) == "full"
    assert resolve_mode({"args": ["--full"], "mode": "partial"}) == "full"


def test_resolve_mode_reads_payload_mode_field():
    assert resolve_mode({"mode": "partial"}) == "partial"
    assert resolve_mode({"mode": " Full "}) == "full"
    assert resolve_mode({"mode": "everything"}) is None
    assert resolve_mode({}) is None


def test_resolve_forced_type_and_scope_validate_input():
    assert resolve_forced_type({"type": "fix"}) == "fix"
    assert resolve_forced_type({"type": " FEAT "}) == "feat"
    assert resolve_forced_type({"type": "banana"}) is None
    assert resolve_forced_type({}) is None
    assert resolve_forced_scope({"scope": " tui "}) == "tui"
    assert resolve_forced_scope({"scope": "  "}) is None
    assert resolve_forced_scope({}) is None


def test_truncate_diff_keeps_short_diffs_and_cuts_on_line_boundary():
    assert truncate_diff("short", 100) == "short"

    long_diff = "\n".join(f"+line {index}" for index in range(100))
    truncated = truncate_diff(long_diff, 200)
    assert len(truncated) <= 200 + len("\n[diff truncated]")
    assert truncated.endswith("[diff truncated]")
    assert "\n+line" in truncated


def test_validate_commit_message_accepts_conventional_subject():
    message, error = validate_commit_message(
        "feat(api): add pagination to list endpoint", _request()
    )
    assert error is None
    assert message == "feat(api): add pagination to list endpoint"


def test_validate_commit_message_preserves_body():
    message, error = validate_commit_message(
        "fix: handle empty payload\n\n- guard against missing keys", _request()
    )
    assert error is None
    assert message == "fix: handle empty payload\n\n- guard against missing keys"


def test_validate_commit_message_rejects_bad_output():
    request = _request()
    cases = {
        "": "empty response",
        "```\nfeat: add thing\n```": "response contains markdown fences",
        "feat: add sparkle ✨": "response contains emoji",
        "Here is the commit message: feat: add x": (
            "response includes introductory text"
        ),
        "just some words": "subject is not a conventional commit",
        "banana: peel the code": "unknown commit type 'banana'",
        "chore: update the project": "subject description is too generic",
    }
    for raw, expected_error in cases.items():
        message, error = validate_commit_message(raw, request)
        assert message is None
        assert error == expected_error


def test_validate_commit_message_rejects_overlong_subject():
    message, error = validate_commit_message("feat: " + "x" * 120, _request())
    assert message is None
    assert "exceeds" in error


def test_validate_commit_message_enforces_forced_type_and_scope():
    request = _request(commit_type="fix", scope="tui")

    message, error = validate_commit_message("feat(tui): add widget", request)
    assert message is None
    assert error == "expected type 'fix'"

    message, error = validate_commit_message("fix(chat): repair widget", request)
    assert message is None
    assert error == "expected scope 'tui'"

    message, error = validate_commit_message("fix(tui): repair widget", request)
    assert error is None
    assert message == "fix(tui): repair widget"


def test_build_commit_message_prompt_includes_stat_diff_and_history():
    request = _request(
        changes=StagedChanges(
            files=[ChangedFile("src/app.py", "modified")],
            stat=" src/app.py | 2 +-",
            diff="+print('hello')",
            recent_subjects=("feat: previous work",),
        )
    )

    messages = build_commit_message_prompt(request)
    assert messages[0]["role"] == "system"
    user_prompt = messages[1]["content"]
    assert "src/app.py | 2 +-" in user_prompt
    assert "print('hello')" in user_prompt
    assert "feat: previous work" in user_prompt


def test_build_commit_message_prompt_includes_constraints_and_hint():
    request = _request(commit_type="fix", scope="tui", hint="commit the tui fix")

    user_prompt = build_commit_message_prompt(request)[1]["content"]
    assert "Required commit type: fix" in user_prompt
    assert "Required commit scope: tui" in user_prompt
    assert "commit the tui fix" in user_prompt


def test_build_commit_message_prompt_escapes_fences_in_untrusted_diff():
    request = _request(
        changes=StagedChanges(
            files=[ChangedFile("notes.md", "modified")],
            stat=" notes.md | 1 +",
            diff="+```bash\n+rm -rf /\n+```",
        )
    )

    user_prompt = build_commit_message_prompt(request)[1]["content"]
    assert "```" not in user_prompt


def test_build_commit_message_prompt_omits_history_when_empty():
    user_prompt = build_commit_message_prompt(_request())[1]["content"]
    assert "Recent commit subject" not in user_prompt


def test_suggest_commit_message_returns_valid_response(monkeypatch):
    class FakeOllama:
        @staticmethod
        def chat(model, messages, options):
            return {"message": {"content": "feat: add pagination"}}

    monkeypatch.setattr(commit_workflow, "_load_ollama", lambda: FakeOllama)
    assert suggest_commit_message(_request()) == "feat: add pagination"


def test_suggest_commit_message_returns_none_when_ollama_unavailable(monkeypatch):
    monkeypatch.setattr(commit_workflow, "_load_ollama", lambda: None)
    assert suggest_commit_message(_request()) is None
    assert "not available" in commit_workflow._last_ollama_error


def test_suggest_commit_message_returns_none_on_ollama_error(monkeypatch):
    class FakeOllama:
        @staticmethod
        def chat(model, messages, options):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(commit_workflow, "_load_ollama", lambda: FakeOllama)
    assert suggest_commit_message(_request()) is None
    assert "connection refused" in commit_workflow._last_ollama_error


def test_suggest_commit_message_repairs_invalid_first_attempt(monkeypatch):
    responses = iter(
        [
            {"message": {"content": "Here is the commit message: feat: add x"}},
            {"message": {"content": "feat: add pagination"}},
        ]
    )
    calls = []

    class FakeOllama:
        @staticmethod
        def chat(model, messages, options):
            calls.append(messages)
            return next(responses)

    monkeypatch.setattr(commit_workflow, "_load_ollama", lambda: FakeOllama)
    assert (
        suggest_commit_message(_request(commit_type="feat")) == "feat: add pagination"
    )
    assert len(calls) == 2
    assert "Validation error" in calls[1][-1]["content"]


def test_suggest_commit_message_gives_up_after_max_attempts(monkeypatch):
    class FakeOllama:
        @staticmethod
        def chat(model, messages, options):
            return {"message": {"content": "not a commit message"}}

    monkeypatch.setattr(commit_workflow, "_load_ollama", lambda: FakeOllama)
    assert suggest_commit_message(_request()) is None
    assert "invalid commit suggestion" in commit_workflow._last_ollama_error


def test_suggest_commit_message_uses_higher_temperature_on_retry(monkeypatch):
    seen_options = []

    class FakeOllama:
        @staticmethod
        def chat(model, messages, options):
            seen_options.append(options)
            return {"message": {"content": "feat: add pagination"}}

    monkeypatch.setattr(commit_workflow, "_load_ollama", lambda: FakeOllama)
    suggest_commit_message(_request(commit_type="feat"), retry=True)
    assert seen_options == [commit_workflow.COMMIT_MESSAGE_RETRY_OPTIONS]


def test_suggest_commit_message_classifies_type_when_not_forced(monkeypatch):
    responses = iter(
        [
            {"message": {"content": "fix"}},
            {"message": {"content": "fix: handle missing key"}},
        ]
    )
    calls = []

    class FakeOllama:
        @staticmethod
        def chat(model, messages, options):
            calls.append(messages)
            return next(responses)

    monkeypatch.setattr(commit_workflow, "_load_ollama", lambda: FakeOllama)
    request = _request()
    assert suggest_commit_message(request) == "fix: handle missing key"
    assert request.commit_type == "fix"
    assert len(calls) == 2
    assert "classify" in calls[0][0]["content"]


def test_classify_commit_type_parses_and_rejects_answers():
    class FakeOllama:
        answer = "fix"

        @classmethod
        def chat(cls, model, messages, options):
            return {"message": {"content": cls.answer}}

    changes = _request().changes
    assert commit_workflow.classify_commit_type(changes, FakeOllama) == "fix"
    FakeOllama.answer = " Refactor. "
    assert commit_workflow.classify_commit_type(changes, FakeOllama) == "refactor"
    FakeOllama.answer = "this is a fix"
    assert commit_workflow.classify_commit_type(changes, FakeOllama) is None


def test_detect_type_from_paths_forces_unambiguous_types():
    detect = commit_workflow.detect_type_from_paths

    def files(*paths):
        return [ChangedFile(path, "modified") for path in paths]

    assert detect(files("tests/test_app.py", "app_spec.ts")) == "test"
    assert detect(files("docs/guide.md", "README.md")) == "docs"
    assert detect(files("pyproject.toml", "poetry.lock")) == "build"
    assert detect(files(".github/workflows/ci.yml")) == "ci"
    assert detect(files("src/app.py", "tests/test_app.py")) is None
    assert detect([]) is None


def test_validate_commit_message_normalizes_llm_quirks():
    request = _request()

    message, error = validate_commit_message("fix: handle empty payload.", request)
    assert error is None
    assert message == "fix: handle empty payload"

    message, error = validate_commit_message(
        "fix: guard reads\n\nfix(script):\n\nExplain the actual change here",
        request,
    )
    assert error is None
    assert message == "fix: guard reads\n\nExplain the actual change here"


def test_validate_commit_message_rejects_pathlike_scope_and_meta_body():
    request = _request()

    message, error = validate_commit_message("fix(src/app.py): guard reads", request)
    assert message is None
    assert "file path" in error

    message, error = validate_commit_message(
        "fix: guard reads\n\n2 files changed, 4 insertions(+)", request
    )
    assert message is None
    assert "diff stat" in error

    message, error = validate_commit_message(
        "fix: guard reads\n\nThe staged change summary indicates a fix.", request
    )
    assert message is None
    assert "explains the message" in error


def test_fallback_commit_message_uses_forced_type_and_scope():
    message = fallback_commit_message(_request(commit_type="fix", scope="tui"))
    assert message == "fix(tui): update app"


def test_fallback_commit_message_detects_docs_and_new_files():
    docs = _request(
        changes=StagedChanges(files=[ChangedFile("docs/guide.md", "modified")])
    )
    assert fallback_commit_message(docs) == "docs: update guide"

    new_files = _request(
        changes=StagedChanges(
            files=[
                ChangedFile("src/widgets/button.py", "new"),
                ChangedFile("src/widgets/panel.py", "new"),
            ]
        )
    )
    assert fallback_commit_message(new_files) == "feat: add widgets"


def test_fallback_commit_message_counts_scattered_files():
    request = _request(
        changes=StagedChanges(
            files=[
                ChangedFile("src/app.py", "modified"),
                ChangedFile("README.md", "modified"),
                ChangedFile("config/settings.py", "deleted"),
            ]
        )
    )
    assert fallback_commit_message(request) == "chore: update 3 files"


# ---------------------------------------------------------------------------
# End-to-end workflow tests against real temporary git repositories.
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("hello\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "chore: initial commit")
    return repo


def _quiet_console() -> Console:
    return Console(file=open("/dev/null", "w"), force_terminal=False)


def _patch_interaction(monkeypatch, *, choices=None, asks=None):
    choice_iter = iter(choices or [])
    ask_iter = iter(asks or [])
    monkeypatch.setattr(commit_workflow, "choose", lambda *a, **k: next(choice_iter))
    monkeypatch.setattr(commit_workflow, "ask", lambda *a, **k: next(ask_iter))


def _patch_suggestion(monkeypatch, message="feat: add generated change"):
    monkeypatch.setattr(
        commit_workflow,
        "suggest_commit_message",
        lambda request, retry=False: message,
    )


def test_run_workflow_errors_outside_git_repository(tmp_path, monkeypatch):
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    monkeypatch.setattr(commit_workflow, "find_repo_root", lambda cwd=None: None)
    assert run_workflow({}, cwd=outside, console=_quiet_console()) == 1


def test_run_workflow_reports_clean_repository(tmp_path):
    repo = _init_repo(tmp_path)
    assert run_workflow({}, cwd=repo, console=_quiet_console()) == 0


def test_run_workflow_full_stages_everything_and_commits(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "app.py").write_text("print('hi')\n")
    (repo / "README.md").write_text("hello world\n")

    _patch_suggestion(monkeypatch)
    _patch_interaction(monkeypatch, choices=["y"])

    assert run_workflow({}, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "log", "-1", "--format=%s") == "feat: add generated change"
    assert _git(repo, "status", "--porcelain") == ""


def test_run_workflow_uses_user_provided_message(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "app.py").write_text("print('hi')\n")

    _patch_interaction(monkeypatch, choices=["y"])
    payload = {"message": "feat(app): add greeting script"}

    assert run_workflow(payload, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "log", "-1", "--format=%s") == "feat(app): add greeting script"


def test_run_workflow_edit_replaces_message(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "app.py").write_text("print('hi')\n")

    _patch_suggestion(monkeypatch)
    _patch_interaction(
        monkeypatch, choices=["edit", "y"], asks=["fix: corrected message"]
    )

    assert run_workflow({}, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "log", "-1", "--format=%s") == "fix: corrected message"


def test_run_workflow_cancel_leaves_changes_staged(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "app.py").write_text("print('hi')\n")

    _patch_suggestion(monkeypatch)
    _patch_interaction(monkeypatch, choices=["cancel"])

    assert run_workflow({}, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "log", "-1", "--format=%s") == "chore: initial commit"
    assert "app.py" in _git(repo, "diff", "--cached", "--name-only")


def test_run_workflow_over_limit_asks_for_mode_and_cancel_stages_nothing(
    tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path)
    for index in range(commit_workflow.FULL_MODE_FILE_LIMIT + 1):
        (repo / f"file_{index}.py").write_text(f"# {index}\n")

    _patch_interaction(monkeypatch, choices=["cancel"])

    assert run_workflow({}, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "diff", "--cached", "--name-only") == ""


def test_run_workflow_over_limit_full_choice_commits_everything(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    file_count = commit_workflow.FULL_MODE_FILE_LIMIT + 2
    for index in range(file_count):
        (repo / f"file_{index}.py").write_text(f"# {index}\n")

    _patch_suggestion(monkeypatch, "feat: add generated batch")
    _patch_interaction(monkeypatch, choices=["full", "y"])

    assert run_workflow({}, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "log", "-1", "--format=%s") == "feat: add generated batch"
    assert _git(repo, "status", "--porcelain") == ""


def test_run_workflow_partial_requires_staged_files(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "app.py").write_text("print('hi')\n")

    payload = {"cli": True, "args": ["--partial"]}
    assert run_workflow(payload, cwd=repo, console=_quiet_console()) == 1
    assert _git(repo, "log", "-1", "--format=%s") == "chore: initial commit"


def test_run_workflow_partial_commits_only_staged_files(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "staged.py").write_text("print('staged')\n")
    (repo / "unstaged.py").write_text("print('unstaged')\n")
    _git(repo, "add", "staged.py")

    _patch_suggestion(monkeypatch, "feat: add staged module")
    _patch_interaction(monkeypatch, choices=["y"])

    payload = {"cli": True, "args": ["--partial"]}
    assert run_workflow(payload, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "log", "-1", "--format=%s") == "feat: add staged module"
    committed = _git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert committed == ["staged.py"]
    assert "unstaged.py" in _git(repo, "status", "--porcelain")


def test_run_workflow_full_flag_skips_mode_prompt(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    for index in range(commit_workflow.FULL_MODE_FILE_LIMIT + 1):
        (repo / f"file_{index}.py").write_text(f"# {index}\n")

    _patch_suggestion(monkeypatch, "feat: add many modules")
    _patch_interaction(monkeypatch, choices=["y"])

    payload = {"cli": True, "args": ["--full"]}
    assert run_workflow(payload, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "status", "--porcelain") == ""


def test_run_workflow_mode_field_from_chat_payload(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "staged.py").write_text("print('staged')\n")
    (repo / "unstaged.py").write_text("print('unstaged')\n")
    _git(repo, "add", "staged.py")

    _patch_suggestion(monkeypatch, "feat: add staged module")
    _patch_interaction(monkeypatch, choices=["y"])

    payload = {"mode": "partial", "raw_text": "commit solo lo staged"}
    assert run_workflow(payload, cwd=repo, console=_quiet_console()) == 0
    committed = _git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert committed == ["staged.py"]


def test_run_workflow_falls_back_when_ollama_unavailable(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("# guide\n")

    monkeypatch.setattr(commit_workflow, "_load_ollama", lambda: None)
    _patch_interaction(monkeypatch, choices=["y"])

    assert run_workflow({}, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "log", "-1", "--format=%s") == "docs: update guide"


def test_run_workflow_retry_regenerates_message(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "app.py").write_text("print('hi')\n")

    suggestions = iter(["feat: first suggestion", "feat: second suggestion"])
    monkeypatch.setattr(
        commit_workflow,
        "suggest_commit_message",
        lambda request, retry=False: next(suggestions),
    )
    _patch_interaction(monkeypatch, choices=["retry", "y"])

    assert run_workflow({}, cwd=repo, console=_quiet_console()) == 0
    assert _git(repo, "log", "-1", "--format=%s") == "feat: second suggestion"


def test_staged_files_reports_statuses(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "added.py").write_text("new\n")
    (repo / "README.md").write_text("changed\n")
    _git(repo, "add", "-A")

    files = {file.path: file.status for file in staged_files(str(repo))}
    assert files == {"added.py": "new", "README.md": "modified"}
