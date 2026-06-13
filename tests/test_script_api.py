import json
import os
import threading
from types import SimpleNamespace

import pytest

import dori.script as script
from dori.script import (
    InteractionCancelled,
    InteractionUnavailable,
    ask,
    choose,
    confirm,
)


@pytest.fixture(autouse=True)
def reset_request_state(monkeypatch):
    monkeypatch.setattr(script, "_next_request_id", 0)


def _set_channel_env(monkeypatch, request_write: int, response_read: int):
    monkeypatch.setenv("DORI_INTERACTION_REQUEST_FD", str(request_write))
    monkeypatch.setenv("DORI_INTERACTION_RESPONSE_FD", str(response_read))


def test_ask_rejects_blank_prompt():
    with pytest.raises(ValueError, match="prompt"):
        ask(" ")


def test_choose_rejects_empty_duplicate_and_invalid_default():
    with pytest.raises(ValueError, match="at least one"):
        choose("Pick", [])
    with pytest.raises(ValueError, match="unique"):
        choose("Pick", ["a", "a"])
    with pytest.raises(ValueError, match="default"):
        choose("Pick", ["a"], default="b")


def test_choose_rejects_string_like_choices():
    with pytest.raises(ValueError, match="sequence of choice strings"):
        choose("Pick", "abc")
    with pytest.raises(ValueError, match="sequence of choice strings"):
        choose("Pick", b"abc")


def test_ask_raises_when_interaction_is_disabled(monkeypatch):
    monkeypatch.setenv("DORI_INTERACTION_DISABLED", "1")

    with pytest.raises(InteractionUnavailable, match="TUI"):
        ask("Name")


def test_confirm_uses_terminal_fallback(monkeypatch):
    monkeypatch.setattr(script.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(script.Confirm, "ask", lambda *args, **kwargs: True)

    assert confirm("Continue?") is True


def test_choose_uses_numeric_terminal_selection(monkeypatch):
    monkeypatch.setattr(script.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(script.Prompt, "ask", lambda *args, **kwargs: "2")

    assert choose("Type", ["feat", "fix"]) == "fix"


def test_choose_uses_case_insensitive_unambiguous_terminal_selection(monkeypatch):
    monkeypatch.setattr(script.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(script.Prompt, "ask", lambda *args, **kwargs: "FIX")

    assert choose("Type", ["feat", "fix"]) == "fix"


def test_choose_raises_interaction_cancelled_on_keyboard_interrupt(monkeypatch):
    monkeypatch.setattr(script.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    def raise_keyboard_interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(script.Prompt, "ask", raise_keyboard_interrupt)

    with pytest.raises(InteractionCancelled, match="cancelled"):
        choose("Type", ["feat", "fix"])


def test_request_requires_both_file_descriptors(monkeypatch):
    monkeypatch.setenv("DORI_INTERACTION_REQUEST_FD", "1")
    monkeypatch.setattr(script.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    with pytest.raises(RuntimeError, match="both request and response"):
        ask("Name")


def test_ask_raises_when_no_channel_and_not_a_tty(monkeypatch):
    monkeypatch.setattr(script.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    with pytest.raises(InteractionUnavailable, match="TUI"):
        ask("Name")


def test_choose_sends_compact_request_and_reads_matching_response(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)

    flushed = []

    class FakeStdout:
        def flush(self):
            flushed.append(True)

    monkeypatch.setattr(script.sys, "stdout", FakeStdout())

    request_bytes: list[bytes] = []

    def reply():
        buffer = bytearray()
        while True:
            chunk = os.read(request_read, 1)
            if chunk == b"\n":
                break
            buffer.extend(chunk)
        request_bytes.append(bytes(buffer))
        request = json.loads(buffer.decode("utf-8"))
        os.write(
            response_write,
            (
                json.dumps(
                    {"version": 1, "id": request["id"], "answer": "fix"},
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8"),
        )

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        assert choose("Type", ["feat", "fix"]) == "fix"
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)

    assert flushed == [True]
    assert b": " not in request_bytes[0]
    request = json.loads(request_bytes[0].decode("utf-8"))
    assert request == {
        "version": 1,
        "id": 1,
        "type": "choose",
        "prompt": "Type",
        "choices": ["feat", "fix"],
        "default": None,
    }


def test_request_retries_until_full_json_line_is_written(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)

    real_write = script.os.write
    writes: list[int] = []

    def partial_write(fd: int, data: bytes) -> int:
        if fd != request_write:
            return real_write(fd, data)

        chunk_size = min(5, len(data))
        writes.append(chunk_size)
        return real_write(fd, data[:chunk_size])

    monkeypatch.setattr(script.os, "write", partial_write)

    request_bytes: list[bytes] = []

    def reply():
        buffer = bytearray()
        while True:
            chunk = os.read(request_read, 1)
            if chunk == b"\n":
                break
            buffer.extend(chunk)
        request_bytes.append(bytes(buffer))
        request = json.loads(buffer.decode("utf-8"))
        os.write(
            response_write,
            (
                json.dumps({"version": 1, "id": request["id"], "answer": "ok"}) + "\n"
            ).encode("utf-8"),
        )

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        assert ask("Name") == "ok"
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)

    assert len(writes) > 1
    request = json.loads(request_bytes[0].decode("utf-8"))
    assert request["type"] == "ask"
    assert request["prompt"] == "Name"


def test_request_raises_for_mismatched_response_id(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)

    def reply():
        request = json.loads(_read_request_line(request_read))
        os.write(
            response_write,
            (
                json.dumps({"version": 1, "id": request["id"] + 1, "answer": "ok"})
                + "\n"
            ).encode("utf-8"),
        )

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        with pytest.raises(RuntimeError, match="mismatched"):
            ask("Name")
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)


def test_request_raises_for_unsupported_response_version(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)

    def reply():
        request = json.loads(_read_request_line(request_read))
        os.write(
            response_write,
            (
                json.dumps({"version": 2, "id": request["id"], "answer": "ok"}) + "\n"
            ).encode("utf-8"),
        )

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        with pytest.raises(
            RuntimeError, match="unsupported interaction protocol version"
        ):
            ask("Name")
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)


def test_request_raises_for_malformed_json_response(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)

    def reply():
        _read_request_line(request_read)
        os.write(response_write, b"{not json}\n")

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        with pytest.raises(RuntimeError, match="malformed"):
            ask("Name")
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)


def test_request_raises_when_response_channel_is_closed(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)
    os.close(response_write)

    def reply():
        _read_request_line(request_read)

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        with pytest.raises(RuntimeError, match="channel closed"):
            ask("Name")
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)


def test_request_raises_when_request_channel_is_closed(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)
    os.close(request_read)

    try:
        with pytest.raises(RuntimeError, match="write"):
            ask("Name")
    finally:
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)


def test_request_raises_interaction_cancelled(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)

    def reply():
        request = json.loads(_read_request_line(request_read))
        os.write(
            response_write,
            (
                json.dumps({"version": 1, "id": request["id"], "cancelled": True})
                + "\n"
            ).encode("utf-8"),
        )

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        with pytest.raises(InteractionCancelled, match="cancelled"):
            ask("Name")
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)


def test_ask_raises_for_non_string_response(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)

    def reply():
        request = json.loads(_read_request_line(request_read))
        os.write(
            response_write,
            (
                json.dumps({"version": 1, "id": request["id"], "answer": True}) + "\n"
            ).encode("utf-8"),
        )

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        with pytest.raises(RuntimeError, match="invalid ask response"):
            ask("Name")
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)


def test_confirm_raises_for_non_bool_response(monkeypatch):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    _set_channel_env(monkeypatch, request_write, response_read)

    def reply():
        request = json.loads(_read_request_line(request_read))
        os.write(
            response_write,
            (
                json.dumps({"version": 1, "id": request["id"], "answer": "yes"}) + "\n"
            ).encode("utf-8"),
        )

    thread = threading.Thread(target=reply)
    thread.start()

    try:
        with pytest.raises(RuntimeError, match="invalid confirm response"):
            confirm("Continue?")
    finally:
        thread.join(timeout=5)
        os.close(request_read)
        os.close(request_write)
        os.close(response_read)
        os.close(response_write)


def _read_request_line(fd: int) -> str:
    buffer = bytearray()
    while True:
        chunk = os.read(fd, 1)
        if chunk == b"\n":
            return buffer.decode("utf-8")
        if not chunk:
            raise RuntimeError("request channel closed unexpectedly")
        buffer.extend(chunk)
