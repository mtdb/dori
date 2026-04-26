import os
import sys

from mnemo8.loader import load_agents, load_skills
from mnemo8.models import RuntimeState
from mnemo8.chat import start_chat


def run():
    """Main entry point for the mnemo8 CLI."""
    try:
        # Step 1: Resolve Current Directory
        cwd = os.getcwd()
        
        # Step 2: Search for AGENTS.md
        agents_content = load_agents(cwd)
        
        # Step 3: Search for skills/
        skills = load_skills(cwd)
        
        # Step 4: Initialize RuntimeState
        state = RuntimeState(
            cwd=cwd,
            agents_content=agents_content,
            skills=skills,
            chat_history=[]
        )
        
        # Step 5: Start chat interface
        start_chat(state)
        
    except Exception as e:
        print(f"Failed to start Mnemo8: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run()
