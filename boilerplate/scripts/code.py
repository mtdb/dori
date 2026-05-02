import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload")
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
        query = payload.get("query", "unknown query")
        language = payload.get("language")

        lang_str = f" [{language}]" if language else ""
        print(f"💻 [Code Search]{lang_str}: Searching code examples for '{query}'...")
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to code script.")
        sys.exit(1)


if __name__ == "__main__":
    main()
