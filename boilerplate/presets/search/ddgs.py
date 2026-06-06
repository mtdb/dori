import json
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to web script.", file=sys.stderr)
        sys.exit(1)

    print("[Web]: DDGS provider placeholder")


if __name__ == "__main__":
    main()
