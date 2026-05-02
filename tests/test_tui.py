import pytest
from mnemo8.tui import _parse_skill, cycle_history, _build_system_prompt
from mnemo8.models import RuntimeState, Skill


# --- _parse_skill ---

def test_parse_skill_plain_json():
    content = '{"skill": "reminders", "time": "9am"}'
    assert _parse_skill(content) == {"skill": "reminders", "time": "9am"}


def test_parse_skill_in_code_block():
    content = 'Sure!\n```json\n{"skill": "calendar"}\n```'
    assert _parse_skill(content) == {"skill": "calendar"}


def test_parse_skill_missing_skill_key():
    assert _parse_skill('{"action": "remind"}') is None


def test_parse_skill_plain_text():
    assert _parse_skill("I believe Paris is the capital.") is None


def test_parse_skill_empty_string():
    assert _parse_skill("") is None


# --- cycle_history ---

def test_cycle_history_up_from_fresh():
    idx, val = cycle_history(["hello", "world"], -1, -1)
    assert idx == 1
    assert val == "world"


def test_cycle_history_up_further():
    idx, val = cycle_history(["hello", "world"], 1, -1)
    assert idx == 0
    assert val == "hello"


def test_cycle_history_up_at_top_stays():
    idx, val = cycle_history(["hello", "world"], 0, -1)
    assert idx == 0
    assert val == "hello"


def test_cycle_history_down_to_fresh():
    idx, val = cycle_history(["hello", "world"], 1, 1)
    assert idx == -1
    assert val == ""


def test_cycle_history_down_from_fresh_does_nothing():
    idx, val = cycle_history(["hello"], -1, 1)
    assert idx == -1
    assert val == ""


def test_cycle_history_empty_list():
    idx, val = cycle_history([], -1, -1)
    assert idx == -1
    assert val == ""


# --- _build_system_prompt ---

def test_build_system_prompt_base():
    state = RuntimeState(cwd="/tmp")
    prompt = _build_system_prompt(state)
    assert "mnemo8" in prompt


def test_build_system_prompt_includes_skill_content():
    state = RuntimeState(
        cwd="/tmp",
        skills=[Skill(name="calendar.md", path="skills/calendar.md", content="# Calendar")],
    )
    prompt = _build_system_prompt(state)
    assert "calendar.md" in prompt
    assert "# Calendar" in prompt


def test_build_system_prompt_includes_agents_content():
    state = RuntimeState(cwd="/tmp", agents_content="You are Nemo.")
    prompt = _build_system_prompt(state)
    assert "You are Nemo." in prompt


def test_build_system_prompt_no_skills_omits_skill_section():
    state = RuntimeState(cwd="/tmp")
    prompt = _build_system_prompt(state)
    assert "--- Skill:" not in prompt
