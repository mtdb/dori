"""
Conversation engine for mnemo8.

Holds all business logic: message history, LLM calls, skill resolution,
and display-text construction.  Both the TUI and the inline CLI use this
module so the behaviour is always identical.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass

import ollama

from mnemo8.models import RuntimeState

# ---------------------------------------------------------------------------
# Skill payload parsing
# ---------------------------------------------------------------------------


def _is_standalone_skill_payload(content: str) -> bool:
    stripped = content.strip()
    if not stripped:
        return False
    if stripped.startswith("{") and stripped.endswith("}"):
        return True
    return bool(re.fullmatch(r"```(?:json)?\s*\{.*?\}\s*```", stripped, re.DOTALL))


def _extract_skill_payload(content: str) -> dict | None:
    parsed = None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    if not isinstance(parsed, dict):
        return None

    skill_name = parsed.get("skill")
    confidence = parsed.get("confidence")

    if not isinstance(skill_name, str) or not skill_name.strip():
        return None

    if confidence is None:
        if not _is_standalone_skill_payload(content):
            return None
        confidence_value = 1.0
    else:
        if isinstance(confidence, bool) or not isinstance(
            confidence, (int, float, str)
        ):
            return None
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            return None

    if not 0.0 <= confidence_value <= 1.0:
        return None

    payload = dict(parsed)
    payload["skill"] = skill_name.strip()
    payload["confidence"] = confidence_value
    return payload


def parse_skill(content: str, min_confidence: float = 0.0) -> dict | None:
    """Return the parsed skill payload if confidence >= min_confidence, else None."""
    payload = _extract_skill_payload(content)
    if payload and payload["confidence"] >= min_confidence:
        return payload
    return None


def strip_skill_payload(content: str) -> str:
    """Remove a skill JSON payload from content, leaving only human-readable text."""
    payload = _extract_skill_payload(content)
    if payload is None:
        return content
    stripped = content.strip()
    try:
        if json.loads(stripped) == payload:
            return ""
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", content, flags=re.DOTALL)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def build_system_prompt(state: RuntimeState) -> str:
    prompt = "You are mnemo8, a helpful personal assistant CLI running on the user's terminal.\n"
    if state.agents_content:
        prompt += f"\nHere is information about your agent configuration:\n{state.agents_content}\n"
    if state.skills:
        prompt += "\nHere are your available skills that you should be aware of:\n"
        prompt += (
            "IMPORTANT: When a skill clearly matches the user's request, respond with a single JSON object only. "
            "Do not add markdown, explanation, or extra prose. The JSON must include the exact skill arguments "
            "plus a numeric 'confidence' field between 0.0 and 1.0. Only emit skill JSON when confidence is at "
            f"least {state.skill_confidence_threshold:.2f}; otherwise answer normally or ask a short clarifying question.\n"
        )
        for skill in state.skills:
            prompt += f"\n--- Skill: {skill.name} ---\n{skill.content}\n"
    return prompt


# ---------------------------------------------------------------------------
# Skill router helpers
# ---------------------------------------------------------------------------


def _build_routing_messages(user_message: str, candidates: list) -> list[dict]:
    options = "\n".join(
        f'- "{s.name}": {s.content.splitlines()[0].lstrip("#").strip()}'
        for s in candidates
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a router. Pick the single best option for the user's request.\n"
                "Respond with a JSON object with keys 'skill' (one of the option names) "
                "and 'confidence' (float 0.0–1.0). No prose, no markdown.\n\n"
                f"Options:\n{options}"
            ),
        },
        {"role": "user", "content": user_message},
    ]


# ---------------------------------------------------------------------------
# Skill execution
# ---------------------------------------------------------------------------


def run_skill(skill_name: str, skill_json: dict) -> str:
    mnemo_home = os.path.expanduser("~/.mnemo8")
    script_path = os.path.join(mnemo_home, "scripts", f"{skill_name}.py")
    if not os.path.isfile(script_path):
        return f"[red]Script for skill '{skill_name}' not found[/red]"
    try:
        result = subprocess.run(
            [sys.executable, script_path, json.dumps(skill_json)],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"[red]{e.stderr.strip()}[/red]"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@dataclass
class ChatResponse:
    """Structured result from a single conversation turn."""

    raw_content: str
    display_text: str
    resolved_skill: dict | None
    skill_output: str | None


class ConversationEngine:
    """
    Stateful conversation engine.

    Holds message history and handles the full turn lifecycle:
    LLM call → skill resolution → router traversal → skill execution →
    display-text construction.
    """

    def __init__(self, state: RuntimeState) -> None:
        self.state = state
        self.messages: list[dict] = [
            {"role": "system", "content": build_system_prompt(state)}
        ]

    async def _descend_router(self, user_message: str, router_skill) -> dict | None:
        """Walk down a router skill tree until a leaf is found."""
        current = router_skill
        while current.is_router:
            routing_messages = _build_routing_messages(user_message, current.children)
            try:
                response = await asyncio.to_thread(
                    ollama.chat, model=self.state.model, messages=routing_messages
                )
            except Exception:
                return None
            payload = parse_skill(
                response["message"]["content"], self.state.skill_confidence_threshold
            )
            if payload is None:
                return None
            matched = next(
                (s for s in current.children if s.name == payload["skill"]), None
            )
            if matched is None:
                return None
            current = matched
        return {"skill": current.name, "confidence": 1.0, "raw_text": user_message}

    async def send(self, user_input: str) -> ChatResponse:
        """
        Send a user message, call Ollama, resolve skills, and return a ChatResponse.

        On Ollama failure, the user message is removed from history and the
        exception is re-raised so the caller can surface an error.
        """
        self.messages.append({"role": "user", "content": user_input})
        try:
            response = await asyncio.to_thread(
                ollama.chat, model=self.state.model, messages=self.messages
            )
        except Exception:
            self.messages.pop()
            raise

        content = response["message"]["content"]
        self.messages.append({"role": "assistant", "content": content})

        # Resolve skill: descend router tree if the LLM picked a non-leaf skill
        resolved_skill = parse_skill(content, self.state.skill_confidence_threshold)
        if resolved_skill:
            matched = next(
                (s for s in self.state.skills if s.name == resolved_skill["skill"]),
                None,
            )
            if matched and matched.is_router:
                resolved_skill = await self._descend_router(user_input, matched)

        # Execute skill and build display text
        skill_output: str | None = None
        if resolved_skill:
            skill_name = resolved_skill["skill"]
            skill_output = await asyncio.to_thread(
                run_skill, skill_name, resolved_skill
            )
            display_text = f"✓ {skill_name}"
            if self.state.debug:
                display_text += f"\n{content}"
            if skill_output:
                display_text += f"\n{skill_output}"
        else:
            display_text = content if self.state.debug else strip_skill_payload(content)
            if not display_text.strip():
                display_text = "I need one more detail before I can choose a skill."

        return ChatResponse(
            raw_content=content,
            display_text=display_text,
            resolved_skill=resolved_skill,
            skill_output=skill_output,
        )

    def pop_last_exchange(self) -> None:
        """Remove the last user + assistant message pair (used by retry)."""
        if len(self.messages) >= 3:
            self.messages.pop()  # assistant
            self.messages.pop()  # user

    def reset(self) -> None:
        """Clear chat history while keeping the system prompt."""
        self.messages = [self.messages[0]]
