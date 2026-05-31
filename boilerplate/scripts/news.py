import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
        query = payload.get("query", "unknown query")
        since = payload.get("since")

        since_str = f" (since: {since})" if since else ""
        print(f"📰 [News Search]: Searching news for '{query}'{since_str}...")
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to news script.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
