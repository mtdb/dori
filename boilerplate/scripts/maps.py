import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload")
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
        place = payload.get("place", "unknown place")
        directions_from = payload.get("directions_from")

        if directions_from:
            print(f"🗺️  [Maps]: Directions from '{directions_from}' to '{place}'...")
        else:
            print(f"📍 [Maps]: Looking up '{place}'...")
    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to maps script.")
        sys.exit(1)


if __name__ == "__main__":
    main()
