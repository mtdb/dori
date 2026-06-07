import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
        title = payload.get("title", "unknown event")
        when = payload.get("when", "unknown time")
        duration = payload.get("duration")
        location = payload.get("location")

        line = f"📅 [Calendar]: '{title}' scheduled for {when}"
        if duration:
            line += f" ({duration})"
        if location:
            line += f" at {location}"
        line += "."
        print(line)
    except json.JSONDecodeError:
        print(
            "Error: Invalid JSON payload provided to calendar script.", file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
