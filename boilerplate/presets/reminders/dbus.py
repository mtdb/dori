import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RELATIVE_TIME_PATTERN = re.compile(
    r"^\s*in\s+(\d+)\s+(seconds?|minutes?|hours?)\s*$",
    re.IGNORECASE,
)


def parse_relative_seconds(when: str) -> int | None:
    match = RELATIVE_TIME_PATTERN.match(when)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("second"):
        return amount
    if unit.startswith("minute"):
        return amount * 60
    if unit.startswith("hour"):
        return amount * 60 * 60
    return None


def _notification_icon_path() -> Path | None:
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir.parent / "assets" / "dori.png",
        script_dir.parent.parent / "assets" / "dori.png",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _notify_send_command(message: str) -> list[str]:
    command = ["notify-send"]
    icon_path = _notification_icon_path()
    if icon_path is not None:
        command.extend(["-i", str(icon_path)])
    command.extend(["Dori reminder", message])
    return command


def schedule_notification(message: str, delay_seconds: int) -> None:
    icon_path = _notification_icon_path()
    if icon_path is None:
        code = (
            "import subprocess, sys, time; "
            "time.sleep(int(sys.argv[1])); "
            'subprocess.run(["notify-send", "Dori reminder", sys.argv[2]], check=False)'
        )
        args = [sys.executable, "-c", code, str(delay_seconds), message]
    else:
        code = (
            "import subprocess, sys, time; "
            "time.sleep(int(sys.argv[1])); "
            'subprocess.run(["notify-send", "-i", sys.argv[3], "Dori reminder", sys.argv[2]], check=False)'
        )
        args = [
            sys.executable,
            "-c",
            code,
            str(delay_seconds),
            message,
            str(icon_path),
        ]
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print(
            "Error: Invalid JSON payload provided to reminders script.",
            file=sys.stderr,
        )
        sys.exit(1)

    message = payload.get("message", "unknown")
    when = payload.get("when", "unknown time")
    seconds = parse_relative_seconds(when)
    if seconds is None:
        print(
            "Error: Unsupported reminder time. Use a relative time like "
            "'in 20 minutes', 'in 2 hours', or 'in 30 seconds'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not payload.get("dry_run", False):
        if shutil.which("notify-send") is None:
            print(
                "Error: D-Bus reminders require notify-send to be installed.",
                file=sys.stderr,
            )
            sys.exit(1)

        schedule_notification(str(message), seconds)

    print(f"[D-Bus]: Scheduled reminder for '{message}' {when}.")


if __name__ == "__main__":
    main()
