import json
import sys

from _commit_workflow import run_workflow

from dori.script import InteractionCancelled


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to commit script.", file=sys.stderr)
        sys.exit(1)

    if not isinstance(payload, dict):
        print("Error: Commit payload must be a JSON object.", file=sys.stderr)
        sys.exit(1)

    try:
        sys.exit(run_workflow(payload))
    except (KeyboardInterrupt, InteractionCancelled):
        print("Cancelled.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
