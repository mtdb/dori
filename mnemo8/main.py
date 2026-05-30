import argparse
import asyncio
import os
import sys

from rich.console import Console
from rich.markup import escape

from mnemo8.chat import ConversationEngine
from mnemo8.commands import init_workspace
from mnemo8.commit_workflow import run_interactive as run_commit_interactive
from mnemo8.loader import (
    get_runtime_home,
    load_agents,
    load_available_vram,
    load_skills,
)
from mnemo8.models import RuntimeState
from mnemo8.tui import start_tui


def _read_debug_flag() -> bool:
    return os.environ.get("MNEMO8_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _read_skill_confidence_threshold() -> float:
    raw_value = os.environ.get("MNEMO8_SKILL_CONFIDENCE_THRESHOLD")
    if raw_value is None:
        return 0.8
    try:
        value = float(raw_value)
    except ValueError:
        return 0.8
    return min(1.0, max(0.0, value))


def run():
    """Main entry point for the Dori CLI."""
    parser = argparse.ArgumentParser(
        description="Dori personal assistant powered by the mnemo8 engine"
    )
    parser.add_argument(
        "-p",
        "--prompt",
        type=str,
        help="Send a single prompt and print the response inline (no TUI).",
        default=None,
    )
    subparsers = parser.add_subparsers(dest="command")

    # Command: init
    subparsers.add_parser("init", help="Initialize Dori with default agents and skills")
    subparsers.add_parser(
        "commit", help="Create conventional commits from local changes"
    )

    args = parser.parse_args()
    cwd = os.getcwd()

    if args.command == "init":
        if args.prompt:
            print("-p/--prompt is not valid with 'init' command.", file=sys.stderr)
            sys.exit(2)
        init_workspace(cwd)
        return

    if args.command == "commit":
        if args.prompt:
            print("-p/--prompt is not valid with 'commit' command.", file=sys.stderr)
            sys.exit(2)
        sys.exit(run_commit_interactive(cwd))

    runtime_home = get_runtime_home()
    if not runtime_home.is_dir():
        print("~/.dori not found. Please run 'dori init' first.", file=sys.stderr)
        sys.exit(1)

    try:
        # Step 2: Search for AGENTS.md
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
    engine = ConversationEngine(state)
    try:
        response = asyncio.run(engine.send(prompt))
    except Exception as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}", highlight=False)
        sys.exit(1)
    console.print(response.display_text, highlight=False)


if __name__ == "__main__":
    run()
