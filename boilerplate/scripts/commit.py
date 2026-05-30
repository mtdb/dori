import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload")
        sys.exit(1)

    try:
        json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to commit script.")
        sys.exit(1)

    print(
        "🔧 [Commit]: This workflow needs an interactive terminal for review and "
        "confirmation. Run `dori commit` from the repository you want to commit."
    )


if __name__ == "__main__":
    main()
