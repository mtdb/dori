from mnemo8.chat import resolve_input


def test_normal_input_returns_itself():
    result, last = resolve_input("hello world", None)
    assert result == "hello world"
    assert last == "hello world"


def test_normal_input_updates_last():
    result, last = resolve_input("new command", "old command")
    assert result == "new command"
    assert last == "new command"


def test_retry_returns_last_instruction():
    result, last = resolve_input("retry", "previous command")
    assert result == "previous command"
    assert last == "previous command"


def test_slash_retry_returns_last_instruction():
    result, last = resolve_input("/retry", "previous command")
    assert result == "previous command"
    assert last == "previous command"


def test_retry_without_history_returns_none():
    result, last = resolve_input("retry", None)
    assert result is None
    assert last is None


def test_retry_case_insensitive():
    result, last = resolve_input("RETRY", "hello")
    assert result == "hello"


def test_retry_with_surrounding_spaces():
    result, last = resolve_input("  /retry  ", "hello")
    assert result == "hello"


def test_consecutive_retries_replay_same_instruction():
    _, last = resolve_input("do something", None)
    result1, last1 = resolve_input("retry", last)
    result2, last2 = resolve_input("retry", last1)
    assert result1 == result2 == "do something"
