import json
import sys

from _commit_workflow import run_interactive


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to commit script.", file=sys.stderr)
        sys.exit(1)

    sys.exit(run_interactive())


if __name__ == "__main__":
    main()
