import json
import sys

from _commit_workflow import run_interactive


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to commit script.", file=sys.stderr)
        sys.exit(1)

    if payload.get("cli") is True:
        sys.exit(run_interactive())

    print(
        "[Commit]: This workflow needs an interactive terminal for review and "
        "confirmation. Run `dori commit` from the repository you want to commit."
    )


if __name__ == "__main__":
    main()
