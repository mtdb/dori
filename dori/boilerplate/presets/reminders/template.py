import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
        message = payload.get("message", "unknown")
        when = payload.get("when", "unknown time")

        # Deterministic output
        print(f"⏰ [System]: I have scheduled a reminder for '{message}' at '{when}'.")
    except json.JSONDecodeError:
        print(
            "Error: Invalid JSON payload provided to reminders script.", file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
