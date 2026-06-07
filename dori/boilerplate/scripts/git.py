import importlib
import json
import os
import re
import subprocess
import sys

ABSTENTION_MESSAGE = (
    "🌿 [Git]: I could not find enough local documentation to answer safely."
)
EXPERT_MODEL_OPTIONS = {"temperature": 0}
ollama = None

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

DOC_TIMEOUT_SECONDS = 3
MAX_DOC_CHARS = 6000


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


def _run_doc_command(cmd: list[str]) -> str | None:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DOC_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None

    output = result.stdout.strip()
    if not output:
        return None

    is_short_help = (
        len(cmd) == 3
        and cmd[0] == "git"
        and cmd[1] in SUPPORTED_COMMANDS
        and cmd[2] == "-h"
    )
    if result.returncode != 0 and not is_short_help:
        return None

    return output[:MAX_DOC_CHARS]


def retrieve_local_docs(command: str) -> str | None:
    if command not in SUPPORTED_COMMANDS:
        return None

    commands = [
        ["git", "help", command],
        ["git", command, "-h"],
        ["man", f"git-{command}"],
    ]

    for cmd in commands:
        docs = _run_doc_command(cmd)
        if docs:
            return docs

    return None


def build_expert_messages(
    topic: str,
    raw_text: str,
    context: str | None,
    docs: str,
) -> list[dict[str, str]]:
    user_lines = [
        f"Untrusted user question: {raw_text}",
        f"Normalized topic: {topic}",
    ]
    if context:
        user_lines.append(f"Untrusted user-provided context: {context}")
    user_lines.append("--- LOCAL GIT DOCUMENTATION START ---")
    user_lines.append(docs)
    user_lines.append("--- LOCAL GIT DOCUMENTATION END ---")

    return [
        {
            "role": "system",
            "content": (
                "You are a read-only Git expert.\n"
                "Answer only from the provided local Git documentation fragments.\n"
                "Do not invent commands, flags, effects, or examples.\n"
                "If the fragments are not enough, say that you could not find "
                "enough local documentation to answer safely.\n"
                "Do not run Git commands.\n"
                "Do not assume the state of the user's repository.\n"
                "Give safe steps and mention risks only when supported by the "
                "documentation.\n"
                "Write in English.\n"
                "Use this format:\n"
                f"🌿 [Git - {topic}]\n"
                "Summary: ...\n"
                "Steps:\n"
                "1. ...\n"
                "Safety notes:\n"
                "- ...\n"
            ),
        },
        {"role": "user", "content": "\n\n".join(user_lines)},
    ]


def _is_usable_answer(answer: str, topic: str) -> bool:
    answer = answer.strip()
    if not answer:
        return False
    lines = answer.splitlines()
    if not lines or lines[0] != f"🌿 [Git - {topic}]":
        return False
    if "Summary:" not in answer:
        return False
    if "Steps:" not in answer:
        return False
    return True


def _load_ollama():
    global ollama
    if ollama is not None:
        return ollama

    script_dir = os.path.dirname(os.path.abspath(__file__))
    original_path = list(sys.path)
    try:
        sys.path = [
            path
            for path in sys.path
            if os.path.abspath(path or os.getcwd()) != script_dir
        ]
        ollama = importlib.import_module("ollama")
    except Exception:
        return None
    finally:
        sys.path = original_path

    return ollama


def generate_answer(
    topic: str,
    raw_text: str,
    context: str | None,
    docs: str,
    model: str = "llama3.1:8b",
) -> str:
    messages = build_expert_messages(topic, raw_text, context, docs)
    ollama_client = _load_ollama()
    if ollama_client is None:
        return ABSTENTION_MESSAGE

    try:
        response = ollama_client.chat(
            model=model,
            messages=messages,
            options=EXPERT_MODEL_OPTIONS,
        )
    except Exception:
        return ABSTENTION_MESSAGE

    answer = response.get("message", {}).get("content", "").strip()
    if not _is_usable_answer(answer, topic):
        return ABSTENTION_MESSAGE
    return answer


def answer_payload(payload: dict) -> str:
    topic_text = str(payload.get("topic") or payload.get("raw_text") or "")
    command = normalize_topic(topic_text)
    if command is None:
        return ABSTENTION_MESSAGE

    docs = retrieve_local_docs(command)
    if not docs:
        return ABSTENTION_MESSAGE

    return generate_answer(
        topic=command,
        raw_text=str(payload.get("raw_text") or topic_text),
        context=payload.get("context"),
        docs=docs,
    )


def main():
    if len(sys.argv) < 2:
        print(ABSTENTION_MESSAGE)
        return

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print(ABSTENTION_MESSAGE)
        return

    if not isinstance(payload, dict):
        print(ABSTENTION_MESSAGE)
        return

    print(answer_payload(payload))


if __name__ == "__main__":
    main()
