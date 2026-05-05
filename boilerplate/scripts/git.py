import json
import sys

GIT_ANSWERS = {
    "cherry-pick": {
        "summary": "Apply a specific commit from another branch onto the current branch.",
        "steps": [
            "Find the commit hash: `git log --oneline <branch>`",
            "Apply it: `git cherry-pick <commit-hash>`",
            "If conflicts arise, resolve them, then: `git cherry-pick --continue`",
            "To abort: `git cherry-pick --abort`",
        ],
    },
    "rebase": {
        "summary": "Move or replay commits on top of another base commit.",
        "steps": [
            "Switch to your branch: `git checkout feature-branch`",
            "Rebase onto target: `git rebase main`",
            "Resolve any conflicts, then: `git rebase --continue`",
            "To abort: `git rebase --abort`",
        ],
    },
    "squash commits": {
        "summary": "Combine multiple commits into one using interactive rebase.",
        "steps": [
            "Start interactive rebase: `git rebase -i HEAD~N` (replace N with number of commits)",
            "In the editor, change `pick` to `squash` (or `s`) for commits to merge",
            "Save and edit the combined commit message",
            "Force-push if already pushed: `git push --force-with-lease`",
        ],
    },
    "stash": {
        "summary": "Temporarily save uncommitted changes to work on something else.",
        "steps": [
            "Save current changes: `git stash`",
            "List stashes: `git stash list`",
            "Apply latest stash (keep it): `git stash apply`",
            "Apply and remove latest stash: `git stash pop`",
            "Apply a specific stash: `git stash apply stash@{2}`",
            "Apply on another branch: switch branch first, then `git stash pop`",
        ],
    },
    "reset vs revert": {
        "summary": "reset rewrites history; revert adds a new commit that undoes changes (safe for shared branches).",
        "steps": [
            "`git reset --soft HEAD~1` — undo last commit, keep changes staged",
            "`git reset --hard HEAD~1` — undo last commit, discard changes (destructive)",
            "`git revert <commit-hash>` — create a new commit that undoes the target commit",
            "Use revert on shared/public branches; use reset on local/private branches only",
        ],
    },
    "merge": {
        "summary": "Combine another branch into the current branch.",
        "steps": [
            "Switch to target branch: `git checkout main`",
            "Merge: `git merge feature-branch`",
            "For a merge commit always: `git merge --no-ff feature-branch`",
            "Resolve conflicts if any, then: `git add . && git commit`",
        ],
    },
    # --- tags ---
    "delete tag": {
        "summary": "Delete a tag locally and/or from the remote.",
        "steps": [
            "Delete locally: `git tag -d <tag-name>`",
            "Delete from remote: `git push origin --delete <tag-name>`",
            "List all tags first: `git tag`",
        ],
    },
    "create tag": {
        "summary": "Create a lightweight or annotated tag.",
        "steps": [
            "Lightweight tag: `git tag <tag-name>`",
            'Annotated tag (recommended): `git tag -a <tag-name> -m "message"`',
            'Tag a specific commit: `git tag -a <tag-name> <commit-hash> -m "message"`',
            "Push the tag: `git push origin <tag-name>`",
            "Push all tags: `git push origin --tags`",
        ],
    },
    "list tags": {
        "summary": "List all tags in the repository.",
        "steps": [
            "List all tags: `git tag`",
            "Filter by pattern: `git tag -l 'v1.*'`",
            "Show tag details: `git show <tag-name>`",
        ],
    },
    "push tag": {
        "summary": "Push a tag to the remote.",
        "steps": [
            "Push a single tag: `git push origin <tag-name>`",
            "Push all local tags: `git push origin --tags`",
        ],
    },
    # --- branches ---
    "create branch": {
        "summary": "Create and switch to a new branch.",
        "steps": [
            "Create and switch: `git checkout -b <branch-name>`",
            "Or with newer syntax: `git switch -c <branch-name>`",
            "Create from a specific commit: `git checkout -b <branch-name> <commit-hash>`",
        ],
    },
    "delete branch": {
        "summary": "Delete a local and/or remote branch.",
        "steps": [
            "Delete local branch (merged): `git branch -d <branch-name>`",
            "Force-delete local branch: `git branch -D <branch-name>`",
            "Delete remote branch: `git push origin --delete <branch-name>`",
        ],
    },
    "rename branch": {
        "summary": "Rename a local branch and update the remote.",
        "steps": [
            "Rename current branch: `git branch -m <new-name>`",
            "Rename a different branch: `git branch -m <old-name> <new-name>`",
            "Push renamed branch and reset upstream: `git push origin -u <new-name>`",
            "Delete the old remote branch: `git push origin --delete <old-name>`",
        ],
    },
    "list branches": {
        "summary": "List local and remote branches.",
        "steps": [
            "Local branches: `git branch`",
            "Remote branches: `git branch -r`",
            "All branches: `git branch -a`",
        ],
    },
    # --- remotes ---
    "add remote": {
        "summary": "Add a new remote to the repository.",
        "steps": [
            "Add remote: `git remote add <name> <url>`",
            "Verify: `git remote -v`",
        ],
    },
    "remove remote": {
        "summary": "Remove a remote from the repository.",
        "steps": [
            "Remove: `git remote remove <name>`",
            "Verify: `git remote -v`",
        ],
    },
    "list remotes": {
        "summary": "List all configured remotes.",
        "steps": [
            "List remotes: `git remote -v`",
            "Show details for one remote: `git remote show origin`",
        ],
    },
}

# Maps alternate phrasings onto canonical keys
ALIASES = {
    "cherry pick": "cherry-pick",
    "cherrypick": "cherry-pick",
    "interactive rebase": "squash commits",
    "squash": "squash commits",
    "remove tag": "delete tag",
    "tag delete": "delete tag",
    "tag remove": "delete tag",
    "add tag": "create tag",
    "make tag": "create tag",
    "tag list": "list tags",
    "show tags": "list tags",
    "new branch": "create branch",
    "make branch": "create branch",
    "remove branch": "delete branch",
    "branch delete": "delete branch",
    "branch rename": "rename branch",
    "move branch": "rename branch",
    "branch list": "list branches",
    "show branches": "list branches",
}

# Keyword pairs for fuzzy matching: if both words appear in the topic, return the key
KEYWORD_RULES: list[tuple[set[str], str]] = [
    ({"delete", "tag"}, "delete tag"),
    ({"remove", "tag"}, "delete tag"),
    ({"create", "tag"}, "create tag"),
    ({"add", "tag"}, "create tag"),
    ({"push", "tag"}, "push tag"),
    ({"list", "tag"}, "list tags"),
    ({"delete", "branch"}, "delete branch"),
    ({"remove", "branch"}, "delete branch"),
    ({"create", "branch"}, "create branch"),
    ({"rename", "branch"}, "rename branch"),
    ({"list", "branch"}, "list branches"),
    ({"add", "remote"}, "add remote"),
    ({"remove", "remote"}, "remove remote"),
    ({"list", "remote"}, "list remotes"),
    ({"squash", "commit"}, "squash commits"),
    ({"reset", "revert"}, "reset vs revert"),
    ({"undo", "commit"}, "reset vs revert"),
    ({"revert", "commit"}, "reset vs revert"),
    ({"undo", "last"}, "reset vs revert"),
    ({"list", "tag"}, "list tags"),
    ({"show", "tag"}, "list tags"),
    ({"new", "branch"}, "create branch"),
    ({"switch", "branch"}, "create branch"),
    ({"show", "remote"}, "list remotes"),
]


def find_answer(text: str) -> dict | None:
    normalized = text.lower().strip()

    if normalized in GIT_ANSWERS:
        return GIT_ANSWERS[normalized]

    if normalized in ALIASES:
        return GIT_ANSWERS[ALIASES[normalized]]

    words = set(normalized.split())
    for keywords, key in KEYWORD_RULES:
        if keywords <= words:
            return GIT_ANSWERS[key]

    for key in GIT_ANSWERS:
        if key in normalized or normalized in key:
            return GIT_ANSWERS[key]

    return None


def find_answer_in_raw(raw_text: str) -> tuple[str, dict] | None:
    """Scan the full raw message for keyword matches when topic extraction failed."""
    t = raw_text.lower()
    for keywords, key in KEYWORD_RULES:
        if all(kw in t for kw in keywords):
            return key, GIT_ANSWERS[key]
    for key in GIT_ANSWERS:
        if key in t:
            return key, GIT_ANSWERS[key]
    return None


def format_answer(topic: str, answer: dict, context: str | None) -> str:
    lines = [f"🌿 [Git — {topic}]: {answer['summary']}"]
    if context:
        lines.append(f"   Context: {context}")
    for step in answer["steps"]:
        lines.append(f"   • {step}")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload")
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
        topic = payload.get("topic", "")
        raw_text = payload.get("raw_text", "")
        context = payload.get("context")

        answer = find_answer(topic) if topic else None

        if not answer:
            result = find_answer_in_raw(raw_text)
            if result:
                topic, answer = result

        if answer:
            print(format_answer(topic, answer, context))
        else:
            display = topic or raw_text or "unknown"
            print(
                f"🌿 [Git — {display}]: No built-in answer found. "
                f"Try: `git help` or https://git-scm.com/docs"
            )

    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to git script.")
        sys.exit(1)


if __name__ == "__main__":
    main()
