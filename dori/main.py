import argparse
import asyncio
import json
import os
import subprocess
import sys

from rich.console import Console
from rich.markup import escape

from dori.chat import ConversationEngine
from dori.commands import (
    init_workspace,
    migrate_legacy_persona_file,
    update_workspace,
)
from dori.loader import (
    get_runtime_home,
    load_agents,
    load_available_vram,
    load_skills,
)
from dori.models import RuntimeState
from dori.tui import start_tui


def _read_debug_flag() -> bool:
    return os.environ.get("DORI_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _read_skill_confidence_threshold() -> float:
    raw_value = os.environ.get("DORI_SKILL_CONFIDENCE_THRESHOLD")
    if raw_value is None:
        return 0.8
    try:
        value = float(raw_value)
    except ValueError:
        return 0.8
    return min(1.0, max(0.0, value))


def run():
    """Main entry point for the Dori CLI."""
    parser = argparse.ArgumentParser(description="Dori personal assistant")
    parser.add_argument(
        "-p",
        "--prompt",
        type=str,
        help="Send a single prompt and print the response inline (no TUI).",
        default=None,
    )
    parser.add_argument(
        "command",
        nargs="?",
        help="Run 'init' or execute an installed skill script by name.",
    )
    parser.add_argument("skill_args", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    cwd = os.getcwd()

    if args.command == "init":
        if args.prompt:
            print("-p/--prompt is not valid with 'init' command.", file=sys.stderr)
            sys.exit(2)
        init_workspace(cwd)
        return

    if args.command == "update":
        if args.prompt:
            print("-p/--prompt is not valid with 'update' command.", file=sys.stderr)
            sys.exit(2)
        update_workspace(cwd)
        return

    if args.command:
        if args.prompt:
            print("-p/--prompt is not valid with skill commands.", file=sys.stderr)
            sys.exit(2)
        sys.exit(run_cli_skill(args.command, args.skill_args, cwd))

    runtime_home = get_runtime_home()
    if not runtime_home.is_dir():
        print("~/.dori not found. Please run 'dori init' first.", file=sys.stderr)
        sys.exit(1)

    try:
        migrate_legacy_persona_file(runtime_home)

        # Step 2: Search for DORI.md
        agents_content = load_agents()

        # Step 3: Search for skills/
        skills = load_skills()
        available_vram_mib, total_vram_mib = load_available_vram()

        # Step 4: Initialize RuntimeState
        state = RuntimeState(
            cwd=cwd,
            agents_content=agents_content,
            skills=skills,
            chat_history=[],
            available_vram_mib=available_vram_mib,
            total_vram_mib=total_vram_mib,
            debug=_read_debug_flag(),
            skill_confidence_threshold=_read_skill_confidence_threshold(),
        )

        if args.prompt:
            # Inline mode: single turn, print response to stdout, no TUI.
            _run_inline(state, args.prompt.strip())
        else:
            # Step 5: Start TUI interface
            start_tui(state)

    except Exception as e:
        print(f"Failed to start Dori: {e}", file=sys.stderr)
        sys.exit(1)


def _run_inline(state: RuntimeState, prompt: str) -> None:
    """Execute a single conversation turn and print the result to stdout."""
    console = Console()
    engine = ConversationEngine(state, allow_script_interaction=False)
    try:
        response = asyncio.run(engine.send(prompt))
    except Exception as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}", highlight=False)
        sys.exit(1)
    console.print(response.display_text, highlight=False)


def run_cli_skill(skill_name: str, skill_args: list[str], cwd: str) -> int:
    if skill_name.startswith("_"):
        print(f"Script for skill '{skill_name}' not found", file=sys.stderr)
        return 1

    runtime_home = get_runtime_home()
    script_path = runtime_home / "scripts" / f"{skill_name}.py"
    if not script_path.is_file():
        print(f"Script for skill '{skill_name}' not found", file=sys.stderr)
        return 1

    raw_text = " ".join(["dori", skill_name, *skill_args]).strip()
    payload = {
        "skill": skill_name,
        "confidence": 1.0,
        "raw_text": raw_text,
        "cli": True,
        "args": skill_args,
    }
    result = subprocess.run(
        [sys.executable, str(script_path), json.dumps(payload)],
        check=False,
        cwd=cwd,
    )
    return result.returncode


if __name__ == "__main__":
    run()
