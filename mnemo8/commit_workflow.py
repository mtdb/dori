from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

EMOJI_FOR_TYPE = {
    "feat": "✨",
    "fix": "🐛",
    "refactor": "♻️",
    "test": "✅",
    "docs": "📝",
    "style": "🎨",
    "perf": "⚡️",
    "chore": "🔧",
    "ci": "👷",
    "build": "📦",
    "revert": "⏪️",
}
ALL_TYPES = list(EMOJI_FOR_TYPE)
STATUS_SYMBOL = {"new": "+", "modified": "~", "deleted": "-", "renamed": "→"}
COMMIT_MESSAGE_MODEL = "llama3.1:8b"
COMMIT_MESSAGE_OPTIONS = {"temperature": 0}
MAX_PROMPT_DIFF_LINES = 80


@dataclass
class ChangedFile:
    path: str
    status: str
    diff: str = ""
    old_path: str | None = None
    index_status: str = " "
    worktree_status: str = " "


@dataclass
class CommitGroup:
    files: list[ChangedFile] = field(default_factory=list)
    commit_type: str | None = None
    scope: str = ""
    emoji: str = ""
    message: str = ""
    amend: bool = False


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _run(
    cmd: list[str],
    *,
    cwd: str | Path | None = None,
    check: bool = False,
) -> CommandResult:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False)
    command_result = CommandResult(result.returncode, result.stdout, result.stderr)
    if check and command_result.returncode != 0:
        raise subprocess.CalledProcessError(
            command_result.returncode,
            cmd,
            output=command_result.stdout,
            stderr=command_result.stderr,
        )
    return command_result


def find_repo_root(cwd: str | Path | None = None) -> str | None:
    result = _run(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    root = result.stdout.strip()
    return root if result.returncode == 0 and root else None


def parse_status_lines(lines: list[str]) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in lines:
        if not line.strip():
            continue

        code = line[:2]
        index_status = code[0]
        worktree_status = code[1]
        path_text = line[3:].strip()
        status = "modified"
        old_path = None
        path = path_text

        if code == "??":
            status = "new"
            index_status = "?"
            worktree_status = "?"
        elif "R" in code and " -> " in path_text:
            status = "renamed"
            old_path, path = [part.strip() for part in path_text.split(" -> ", 1)]
        elif "A" in code:
            status = "new"
        elif "D" in code:
            status = "deleted"

        files.append(
            ChangedFile(
                path=path,
                status=status,
                old_path=old_path,
                index_status=index_status,
                worktree_status=worktree_status,
            )
        )
    return files


def scan_changes(repo_root: str) -> tuple[list[ChangedFile], list[str]]:
    status = _run(["git", "status", "--porcelain"], cwd=repo_root)
    if not status.stdout.strip():
        return [], []

    files = parse_status_lines(status.stdout.splitlines())
    for changed_file in files:
        diff_path = changed_file.old_path or changed_file.path
        diff = _run(
            ["git", "diff", "HEAD", "--", diff_path, changed_file.path], cwd=repo_root
        )
        if not diff.stdout.strip():
            diff = _run(
                ["git", "diff", "--cached", "--", diff_path, changed_file.path],
                cwd=repo_root,
            )
        changed_file.diff = "\n".join(diff.stdout.splitlines()[:200])

    log = _run(["git", "log", "--oneline", "-5", "--format=%s"], cwd=repo_root)
    last_commits = [line.strip() for line in log.stdout.splitlines() if line.strip()]
    return files, last_commits


def _module_key(path: str) -> str:
    parts = [part for part in Path(path).parts if part not in {"src", "app", "lib"}]
    if not parts:
        return path
    if parts[0] in {"tests", "test"} and len(parts) > 1:
        return parts[1]
    return parts[0]


def group_files(files: list[ChangedFile]) -> list[list[ChangedFile]]:
    if not files:
        return []

    groups: list[list[ChangedFile]] = []
    remaining = list(files)
    claimed: set[str] = set()

    module_map: dict[str, list[ChangedFile]] = {}
    for changed_file in remaining:
        module_map.setdefault(_module_key(changed_file.path), []).append(changed_file)

    for module_files in module_map.values():
        if len(module_files) > 1:
            groups.append(module_files)
            claimed.update(changed_file.path for changed_file in module_files)

    remaining = [
        changed_file for changed_file in remaining if changed_file.path not in claimed
    ]

    stem_map: dict[str, list[ChangedFile]] = {}
    for changed_file in remaining:
        stem_map.setdefault(_matching_stem(changed_file.path), []).append(changed_file)

    for stem_files in stem_map.values():
        has_test = any(_is_test_path(changed_file.path) for changed_file in stem_files)
        has_non_test = any(
            not _is_test_path(changed_file.path) for changed_file in stem_files
        )
        if len(stem_files) > 1 and has_test and has_non_test:
            groups.append(stem_files)
            claimed.update(changed_file.path for changed_file in stem_files)

    remaining = [
        changed_file for changed_file in remaining if changed_file.path not in claimed
    ]

    matchers = (
        lambda file: _is_test_path(file.path),
        lambda file: _is_root_config(file.path),
        lambda file: "migrations" in Path(file.path).parts,
    )
    for matcher in matchers:
        matched = [changed_file for changed_file in remaining if matcher(changed_file)]
        if matched:
            groups.append(matched)
            matched_paths = {changed_file.path for changed_file in matched}
            remaining = [
                changed_file
                for changed_file in remaining
                if changed_file.path not in matched_paths
            ]

    by_parent: dict[str, list[ChangedFile]] = {}
    for changed_file in remaining:
        by_parent.setdefault(str(Path(changed_file.path).parent), []).append(
            changed_file
        )
    groups.extend(by_parent.values())
    return groups


def _is_test_path(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")


def _matching_stem(path: str) -> str:
    stem = Path(path).stem
    if stem.startswith("test_"):
        return stem.removeprefix("test_")
    if stem.endswith("_test"):
        return stem.removesuffix("_test")
    return stem


def _is_root_config(path: str) -> bool:
    parsed = Path(path)
    return parsed.parent == Path(".") and parsed.suffix in {
        ".cfg",
        ".ini",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
    }


def detect_type(files: list[ChangedFile]) -> str | None:
    paths = [changed_file.path for changed_file in files]
    statuses = {changed_file.status for changed_file in files}

    if all(_is_test_path(path) for path in paths):
        return "test"
    if any(".github" in Path(path).parts for path in paths):
        return "ci"
    if all("migrations" in Path(path).parts for path in paths):
        return "chore"
    if all(path.endswith(".md") or "docs" in Path(path).parts for path in paths):
        return "docs"
    if all(Path(path).name in {"pyproject.toml", "poetry.lock"} for path in paths):
        return "build"
    if statuses == {"new"}:
        return "feat"
    if statuses == {"modified"}:
        return "fix"
    if statuses == {"deleted"}:
        return "refactor"
    return None


def detect_scope(files: list[ChangedFile]) -> str:
    noise = {"src", "app", "lib", "tests", "test"}
    meaningful_roots: list[str] = []
    parents: list[str] = []

    for changed_file in files:
        path = Path(changed_file.path)
        parts = [part for part in path.parts[:-1] if part not in noise]
        if parts:
            meaningful_roots.append(parts[0])
        parents.append(str(path.parent))

    if meaningful_roots and len(set(meaningful_roots)) == 1:
        return meaningful_roots[0]
    if parents and len(set(parents)) == 1 and parents[0] != ".":
        return Path(parents[0]).name
    return ""


def is_last_commit_pushed(repo_root: str) -> bool:
    result = _run(["git", "log", "@{u}..HEAD", "--oneline"], cwd=repo_root)
    if result.returncode != 0:
        return False
    return result.stdout.strip() == ""


def amend_qualifies(
    last_subject: str, commit_type: str, scope: str, pushed: bool
) -> bool:
    if pushed:
        return False
    match = re.match(r"^(\w+)(?:\(([^)]*)\))?[!]?:", last_subject)
    if match is None:
        return False
    return match.group(1) == commit_type and (match.group(2) or "") == scope


def build_commit_message(group: CommitGroup) -> str:
    commit_type = group.commit_type or "chore"
    emoji = group.emoji or EMOJI_FOR_TYPE.get(commit_type, "🔧")
    scope = f"({group.scope})" if group.scope else ""
    verb = _subject_verb(commit_type)
    target = _message_target(group.files, group.scope)
    subject = f"{commit_type}{scope}: {emoji} {verb} {target}".strip()

    if len(group.files) == 1:
        return subject

    body_lines = [
        f"{_body_emoji(changed_file)} {_body_description(changed_file)}"
        for changed_file in group.files[:6]
    ]
    return subject + "\n\n" + "\n".join(body_lines)


def build_commit_message_prompt(group: CommitGroup) -> list[dict[str, str]]:
    commit_type = group.commit_type or "chore"
    emoji = group.emoji or EMOJI_FOR_TYPE.get(commit_type, "🔧")
    scope = group.scope or ""
    file_sections: list[str] = []

    for changed_file in group.files:
        path_line = f"{changed_file.status} {changed_file.path}"
        if changed_file.old_path:
            path_line = f"{path_line} (renamed from {changed_file.old_path})"

        diff_lines = changed_file.diff.splitlines()[:MAX_PROMPT_DIFF_LINES]
        diff_text = "\n".join(diff_lines).strip() or "(no diff available)"
        file_sections.append(f"{path_line}\n```diff\n{diff_text}\n```")

    user_prompt = "\n\n".join(
        [
            f"Detected type: {commit_type}",
            f"Detected scope: {scope or '(none)'}",
            f"Expected emoji: {emoji}",
            "Changed files:",
            "\n\n".join(file_sections),
        ]
    )

    return [
        {
            "role": "system",
            "content": (
                "You write high-quality git commit messages.\n"
                "Output only the commit message, with no markdown fences, "
                "no explanations, and no surrounding quotes.\n"
                "Use conventional commits format.\n"
                "Use the detected type and scope exactly when provided.\n"
                "Include the expected emoji after the colon.\n"
                "Use imperative mood and describe the behavior change.\n"
                "Avoid generic subjects like 'update folder', 'update files', "
                "or 'update project'."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]


def _subject_verb(commit_type: str) -> str:
    return {
        "feat": "add",
        "fix": "update",
        "refactor": "refactor",
        "test": "update",
        "docs": "update",
        "style": "format",
        "perf": "optimize",
        "chore": "update",
        "ci": "update",
        "build": "update",
        "revert": "revert",
    }.get(commit_type, "update")


def _message_target(files: list[ChangedFile], scope: str) -> str:
    if scope:
        return scope.replace("_", " ")
    if len(files) == 1:
        return Path(files[0].path).stem.replace("_", " ")
    common_parent = Path(files[0].path).parent
    if common_parent != Path(".") and all(
        Path(file.path).parent == common_parent for file in files
    ):
        return common_parent.name.replace("_", " ")
    return "project files"


def _body_emoji(changed_file: ChangedFile) -> str:
    if changed_file.status == "new":
        return "✨"
    if changed_file.status == "deleted":
        return "🔥"
    if changed_file.status == "renamed":
        return "🚚"
    if _is_test_path(changed_file.path):
        return "✅"
    if changed_file.path.endswith(".md"):
        return "📝"
    return "🔧"


def _body_description(changed_file: ChangedFile) -> str:
    action = {
        "new": "add",
        "modified": "update",
        "deleted": "remove",
        "renamed": "rename",
    }.get(changed_file.status, "update")
    return f"{action} {changed_file.path}"


def stage_group(group: CommitGroup, repo_root: str) -> CommandResult:
    add_all_paths: list[str] = []
    update_paths: list[str] = []
    for changed_file in group.files:
        already_staged_only = (
            changed_file.index_status in {"D", "R"}
            and changed_file.worktree_status == " "
        )
        if already_staged_only:
            continue

        if changed_file.status == "deleted":
            update_paths.append(changed_file.path)
            continue

        if changed_file.old_path:
            add_all_paths.append(changed_file.old_path)
        add_all_paths.append(changed_file.path)

    combined = CommandResult(0)
    if update_paths:
        combined = _run(["git", "add", "-u", "--", *update_paths], cwd=repo_root)
        if combined.returncode != 0:
            return combined
    if add_all_paths:
        add_result = _run(["git", "add", "-A", "--", *add_all_paths], cwd=repo_root)
        return CommandResult(
            add_result.returncode,
            combined.stdout + add_result.stdout,
            combined.stderr + add_result.stderr,
        )
    return combined


def commit_group(group: CommitGroup, repo_root: str) -> tuple[str | None, str]:
    stage_result = stage_group(group, repo_root)
    if stage_result.returncode != 0:
        return None, stage_result.stdout + stage_result.stderr

    cmd = ["git", "commit"]
    if group.amend:
        cmd.append("--amend")
    cmd.extend(["-m", group.message])

    result = _run(cmd, cwd=repo_root)
    if result.returncode == 0:
        sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, check=True)
        return sha.stdout.strip(), result.stdout + result.stderr

    retry_sha, retry_output = retry_after_hook_fix(group, repo_root)
    if retry_sha:
        return retry_sha, result.stdout + result.stderr + retry_output
    return None, result.stdout + result.stderr + retry_output


def retry_after_hook_fix(group: CommitGroup, repo_root: str) -> tuple[str | None, str]:
    stage_result = stage_group(group, repo_root)
    if stage_result.returncode != 0:
        return None, stage_result.stdout + stage_result.stderr

    cmd = ["git", "commit"]
    if group.amend:
        cmd.append("--amend")
    cmd.extend(["-m", group.message])
    result = _run(cmd, cwd=repo_root)
    if result.returncode != 0:
        return None, result.stdout + result.stderr
    sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, check=True)
    return sha.stdout.strip(), result.stdout + result.stderr


def run_interactive(
    cwd: str | Path | None = None, console: Console | None = None
) -> int:
    console = console or Console()
    repo_root = find_repo_root(cwd)
    if repo_root is None:
        console.print("[red]Error:[/red] not in a git repository.", highlight=False)
        return 1

    files, last_commits = scan_changes(repo_root)
    if not files:
        console.print("No changes to commit.")
        return 0

    groups = [
        CommitGroup(
            files=group,
            commit_type=detect_type(group),
            scope=detect_scope(group),
        )
        for group in group_files(files)
    ]
    for group in groups:
        group.emoji = EMOJI_FOR_TYPE.get(group.commit_type or "", "🔧")

    if len(groups) == 1 and groups[0].commit_type:
        pushed = is_last_commit_pushed(repo_root)
        last_subject = last_commits[0] if last_commits else ""
        if amend_qualifies(
            last_subject, groups[0].commit_type, groups[0].scope, pushed
        ):
            groups[0].amend = Confirm.ask(
                f"Last commit was '{last_subject}'. Amend it?",
                default=False,
                console=console,
            )

    created: list[tuple[str, str]] = []
    for index, group in enumerate(groups, 1):
        if not _review_group(group, index, len(groups), console):
            continue
        sha, output = commit_group(group, repo_root)
        if sha is None:
            console.print("[red]Commit failed.[/red]", highlight=False)
            if output.strip():
                console.print(output.strip(), highlight=False)
            return 1
        subject = group.message.splitlines()[0]
        created.append((sha, subject))
        console.print(f"[green]Committed[/green] {sha} {subject}", highlight=False)

    if not created:
        console.print("No commits created.")
        return 0

    console.print(f"\nDone. Created {len(created)} commit(s):", highlight=False)
    for sha, subject in created:
        console.print(f"  {sha}  {subject}", highlight=False)
    return 0


def _review_group(group: CommitGroup, index: int, total: int, console: Console) -> bool:
    _show_group(group, index, total, console)
    if group.commit_type is None:
        console.print(
            "Could not auto-detect commit type. Pick one to generate a message."
        )
        group.commit_type = _ask_commit_type(console)
        group.emoji = EMOJI_FOR_TYPE.get(group.commit_type, "🔧")
    group.message = build_commit_message(group)

    while True:
        console.print("\nSuggested commit message:", style="bold")
        console.print(group.message, highlight=False)

        answer = Prompt.ask(
            "Commit this group?",
            choices=["y", "n", "type", "scope", "message", "skip"],
            default="y",
            console=console,
        )
        if answer == "y":
            return True
        if answer in {"n", "skip"}:
            return False
        if answer == "type":
            group.commit_type = _ask_commit_type(console)
            group.emoji = EMOJI_FOR_TYPE.get(group.commit_type, "🔧")
            group.message = build_commit_message(group)
        if answer == "scope":
            group.scope = Prompt.ask("Scope", default="", console=console).strip()
            group.message = build_commit_message(group)
        if answer == "message":
            group.message = _read_multiline_message(console)


def _show_group(group: CommitGroup, index: int, total: int, console: Console) -> None:
    scope = f"({group.scope})" if group.scope else ""
    commit_type = group.commit_type or "?"
    emoji = group.emoji or "?"
    console.print(f"\nGroup {index}/{total} -> {commit_type}{scope}: {emoji}")
    for changed_file in group.files:
        symbol = STATUS_SYMBOL.get(changed_file.status, "?")
        console.print(f"  {symbol} {changed_file.path}")


def _ask_commit_type(console: Console) -> str:
    for index, commit_type in enumerate(ALL_TYPES, 1):
        console.print(f"  {index}. {commit_type} {EMOJI_FOR_TYPE[commit_type]}")
    while True:
        answer = Prompt.ask("Commit type", console=console).strip()
        if answer.isdigit() and 1 <= int(answer) <= len(ALL_TYPES):
            return ALL_TYPES[int(answer) - 1]
        if answer in ALL_TYPES:
            return answer
        console.print("Invalid type.", highlight=False)


def _read_multiline_message(console: Console) -> str:
    console.print("Enter commit message. Finish with a line containing only '.'.")
    lines: list[str] = []
    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        stripped = line.rstrip("\n")
        if stripped == ".":
            break
        lines.append(stripped)
    return "\n".join(lines).strip()
