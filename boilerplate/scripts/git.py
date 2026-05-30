import json
import re
import sys

ABSTENTION_MESSAGE = (
    "🌿 [Git]: I could not find enough local documentation to answer safely."
)

SUPPORTED_COMMANDS = (
    "cherry-pick",
    "rebase",
    "stash",
    "branch",
    "tag",
    "remote",
    "reset",
    "revert",
    "merge",
    "log",
    "diff",
    "status",
    "commit",
    "checkout",
    "switch",
    "restore",
)

PHRASE_COMMANDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("squash", "commit"), "rebase"),
    (("interactive", "rebase"), "rebase"),
    (("cherry", "pick"), "cherry-pick"),
    (("cherry-pick",), "cherry-pick"),
    (("delete", "branch"), "branch"),
    (("remove", "branch"), "branch"),
    (("remote", "branch"), "branch"),
    (("delete", "tag"), "tag"),
    (("remove", "tag"), "tag"),
    (("undo", "commit", "safely"), "revert"),
    (("undo", "commit"), "revert"),
    (("reset", "revert"), "revert"),
    (("show", "changes"), "diff"),
    (("changes", "before", "commit"), "diff"),
    (("move", "work"), "stash"),
)


def _tokens(text: str) -> set[str]:
    normalized = text.lower().replace("_", "-")
    words = set(re.findall(r"[a-z0-9-]+", normalized))
    words.update(word[:-1] for word in list(words) if word.endswith("s"))
    return words


def normalize_topic(topic: str) -> str | None:
    words = _tokens(topic)
    if not words:
        return None

    for required_words, command in PHRASE_COMMANDS:
        if all(word in words for word in required_words):
            return command

    for command in SUPPORTED_COMMANDS:
        if command in words:
            return command

    return None


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload")
        sys.exit(1)

    try:
        json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to git script.")
        sys.exit(1)

    print(ABSTENTION_MESSAGE)


if __name__ == "__main__":
    main()
