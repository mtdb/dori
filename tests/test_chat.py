"""
Tests for the conversation engine (mnemo8.chat).

These tests cover business logic: skill parsing, system prompt construction,
skill execution, and the full ConversationEngine.send() turn lifecycle.
"""

import asyncio
from unittest.mock import patch

import pytest

from mnemo8.chat import (
    ChatResponse,
    ConversationEngine,
    build_system_prompt,
    parse_skill,
    strip_skill_payload,
)
from mnemo8.models import RuntimeState, Skill

# ---------------------------------------------------------------------------
# parse_skill
# ---------------------------------------------------------------------------


def test_parse_skill_plain_json():
    content = '{"skill": "reminders", "time": "9am", "confidence": 0.95}'
    assert parse_skill(content) == {
        "skill": "reminders",
        "time": "9am",
        "confidence": 0.95,
    }


def test_parse_skill_in_code_block():
    content = '```json\n{"skill": "calendar", "confidence": 0.85}\n```'
    assert parse_skill(content) == {"skill": "calendar", "confidence": 0.85}


def test_parse_skill_missing_skill_key():
    assert parse_skill('{"action": "remind", "confidence": 0.9}') is None


def test_parse_skill_missing_confidence_uses_legacy_standalone_json():
    assert parse_skill('{"skill": "reminders", "time": "9am"}') == {
        "skill": "reminders",
        "time": "9am",
        "confidence": 1.0,
    }


def test_parse_skill_missing_confidence_with_prose_is_ignored():
    assert (
        parse_skill('Claro:\n```json\n{"skill": "reminders", "time": "9am"}\n```')
        is None
    )


def test_parse_skill_below_threshold_is_ignored():
    content = '{"skill": "search", "query": "shakira", "confidence": 0.79}'
    assert parse_skill(content, min_confidence=0.8) is None


def test_parse_skill_plain_text():
    assert parse_skill("I believe Paris is the capital.") is None


def test_parse_skill_empty_string():
    assert parse_skill("") is None


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_base():
    state = RuntimeState(cwd="/tmp")
    prompt = build_system_prompt(state)
    assert "You are Dori" in prompt
    assert "mnemo8 engine" in prompt


def test_build_system_prompt_includes_skill_content():
    state = RuntimeState(
        cwd="/tmp",
        skills=[
            Skill(name="calendar.md", path="skills/calendar.md", content="# Calendar")
        ],
    )
    prompt = build_system_prompt(state)
    assert "calendar.md" in prompt
    assert "# Calendar" in prompt
    assert "confidence" in prompt


def test_build_system_prompt_includes_agents_content():
    state = RuntimeState(cwd="/tmp", agents_content="You are Dori.")
    prompt = build_system_prompt(state)
    assert "You are Dori." in prompt


def test_build_system_prompt_no_skills_omits_skill_section():
    state = RuntimeState(cwd="/tmp")
    prompt = build_system_prompt(state)
    assert "--- Skill:" not in prompt


# ---------------------------------------------------------------------------
# strip_skill_payload
# ---------------------------------------------------------------------------


def test_strip_skill_payload_removes_standalone_json():
    assert strip_skill_payload('{"skill": "search", "confidence": 0.9}') == ""


def test_strip_skill_payload_removes_json_code_block():
    result = strip_skill_payload(
        'Sure thing.\n```json\n{"skill": "calendar", "confidence": 0.9}\n```'
    )
    assert result == "Sure thing."


def test_strip_skill_payload_leaves_plain_text_unchanged():
    assert strip_skill_payload("Here is the answer.") == "Here is the answer."


# ---------------------------------------------------------------------------
# ConversationEngine — send()
# ---------------------------------------------------------------------------


def _make_ollama_response(content: str) -> dict:
    return {"message": {"content": content}}


def test_engine_send_plain_response():
    state = RuntimeState(cwd="/tmp")
    engine = ConversationEngine(state)

    with patch("mnemo8.chat.ollama.chat", return_value=_make_ollama_response("Paris.")):
        response = asyncio.run(engine.send("What is the capital of France?"))

    assert isinstance(response, ChatResponse)
    assert response.raw_content == "Paris."
    assert response.display_text == "Paris."
    assert response.resolved_skill is None
    assert response.skill_output is None


def test_engine_send_appends_to_history():
    state = RuntimeState(cwd="/tmp")
    engine = ConversationEngine(state)

    with patch("mnemo8.chat.ollama.chat", return_value=_make_ollama_response("Hi!")):
        asyncio.run(engine.send("Hello"))

    assert engine.messages[1] == {"role": "user", "content": "Hello"}
    assert engine.messages[2] == {"role": "assistant", "content": "Hi!"}


def test_engine_send_removes_user_message_on_ollama_error():
    state = RuntimeState(cwd="/tmp")
    engine = ConversationEngine(state)

    with patch("mnemo8.chat.ollama.chat", side_effect=RuntimeError("conn failed")):
        with pytest.raises(RuntimeError):
            asyncio.run(engine.send("Hello"))

    # Only the system message should remain
    assert len(engine.messages) == 1


def test_engine_send_executes_high_confidence_skill():
    state = RuntimeState(cwd="/tmp", skill_confidence_threshold=0.8)
    engine = ConversationEngine(state)

    raw = '{"skill": "search", "query": "Madrid weather", "confidence": 0.92}'
    with (
        patch("mnemo8.chat.ollama.chat", return_value=_make_ollama_response(raw)),
        patch("mnemo8.chat.run_skill", return_value="22°C, sunny") as mock_run,
    ):
        response = asyncio.run(engine.send("What's the weather in Madrid?"))

    mock_run.assert_called_once()
    assert response.resolved_skill is not None
    assert response.resolved_skill["skill"] == "search"
    assert response.skill_output == "22°C, sunny"
    assert "✓ search" in response.display_text
    assert "22°C, sunny" in response.display_text
    assert '"skill"' not in response.display_text


def test_engine_send_ignores_low_confidence_skill():
    state = RuntimeState(cwd="/tmp", skill_confidence_threshold=0.8)
    engine = ConversationEngine(state)

    raw = '{"skill": "search", "query": "Madrid weather", "confidence": 0.42}'
    with (
        patch("mnemo8.chat.ollama.chat", return_value=_make_ollama_response(raw)),
        patch("mnemo8.chat.run_skill") as mock_run,
    ):
        response = asyncio.run(engine.send("What's the weather?"))

    mock_run.assert_not_called()
    assert response.resolved_skill is None


def test_engine_send_shows_raw_json_in_debug_mode():
    state = RuntimeState(cwd="/tmp", debug=True, skill_confidence_threshold=0.8)
    engine = ConversationEngine(state)

    raw = '{"skill": "search", "query": "news", "confidence": 0.9}'
    with (
        patch("mnemo8.chat.ollama.chat", return_value=_make_ollama_response(raw)),
        patch("mnemo8.chat.run_skill", return_value="some result"),
    ):
        response = asyncio.run(engine.send("latest news"))

    assert raw in response.display_text


def test_engine_send_returns_fallback_when_display_is_empty():
    state = RuntimeState(cwd="/tmp", skill_confidence_threshold=0.8)
    engine = ConversationEngine(state)

    # Standalone JSON with no prose → strip_skill_payload returns "" → fallback
    raw = '{"skill": "search", "query": "x", "confidence": 0.3}'
    with patch("mnemo8.chat.ollama.chat", return_value=_make_ollama_response(raw)):
        response = asyncio.run(engine.send("x"))

    assert (
        response.display_text == "I need one more detail before I can choose a skill."
    )


def test_engine_send_returns_clarify_when_required_fields_missing():
    state = RuntimeState(
        cwd="/tmp",
        skill_confidence_threshold=0.8,
        skills=[
            Skill(name="calendar", path="skills/calendar.md", content="# Calendar")
        ],
    )
    engine = ConversationEngine(state)

    raw = '{"skill": "calendar", "confidence": 0.95}'
    with (
        patch("mnemo8.chat.ollama.chat", return_value=_make_ollama_response(raw)),
        patch("mnemo8.chat.run_skill") as mock_run,
    ):
        response = asyncio.run(engine.send("Schedule team sync tomorrow"))

    mock_run.assert_not_called()
    assert response.resolved_skill is None
    assert response.display_text.startswith("I need ")


def test_engine_send_extracts_git_payload_when_topic_missing():
    state = RuntimeState(
        cwd="/tmp",
        skill_confidence_threshold=0.8,
        skills=[
            Skill(name="git", path="devtools/git.md", content="# Git Expert Skill")
        ],
    )
    engine = ConversationEngine(state)

    responses = [
        _make_ollama_response('{"skill": "git", "confidence": 0.95}'),
        _make_ollama_response(
            '{"skill": "git", "confidence": 0.95, "topic": "rebase", "raw_text": "How do I squash commits?"}'
        ),
    ]

    with (
        patch("mnemo8.chat.ollama.chat", side_effect=responses),
        patch(
            "mnemo8.chat.run_skill", return_value="🌿 [Git - rebase]\nSummary: ok"
        ) as mock_run,
    ):
        response = asyncio.run(engine.send("How do I squash commits?"))

    mock_run.assert_called_once()
    assert response.resolved_skill is not None
    assert response.resolved_skill["skill"] == "git"
    assert response.resolved_skill["topic"] == "rebase"
    assert "🌿 [Git - rebase]" in response.display_text


# ---------------------------------------------------------------------------
# ConversationEngine — pop_last_exchange / reset
# ---------------------------------------------------------------------------


def test_engine_pop_last_exchange_removes_two_messages():
    state = RuntimeState(cwd="/tmp")
    engine = ConversationEngine(state)
    engine.messages += [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    engine.pop_last_exchange()
    assert len(engine.messages) == 1  # only system prompt


def test_engine_pop_last_exchange_noop_when_only_system_prompt():
    state = RuntimeState(cwd="/tmp")
    engine = ConversationEngine(state)
    engine.pop_last_exchange()  # should not raise
    assert len(engine.messages) == 1


def test_engine_reset_keeps_system_prompt():
    state = RuntimeState(cwd="/tmp")
    engine = ConversationEngine(state)
    engine.messages += [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    engine.reset()
    assert len(engine.messages) == 1
    assert engine.messages[0]["role"] == "system"
