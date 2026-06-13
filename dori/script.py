from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from rich.prompt import Confirm, Prompt

_REQUEST_FD_ENV = "DORI_INTERACTION_REQUEST_FD"
_RESPONSE_FD_ENV = "DORI_INTERACTION_RESPONSE_FD"
_DISABLED_ENV = "DORI_INTERACTION_DISABLED"
_PROTOCOL_VERSION = 1
_next_request_id = 0


class InteractionUnavailable(RuntimeError):  # noqa: N818
    """Raised when a script requests input in a one-shot environment."""


class InteractionCancelled(RuntimeError):  # noqa: N818
    """Raised when the active workflow is cancelled."""


def ask(prompt: str, default: str | None = None) -> str:
    validated_prompt = _validate_prompt(prompt)
    response = _request({"type": "ask", "prompt": validated_prompt, "default": default})
    if response is None:
        try:
            return Prompt.ask(validated_prompt, default=default)
        except KeyboardInterrupt as error:
            raise InteractionCancelled("Dori interaction was cancelled.") from error
    return _require_string_answer(response, "ask")


def confirm(prompt: str, default: bool = False) -> bool:
    validated_prompt = _validate_prompt(prompt)
    response = _request(
        {"type": "confirm", "prompt": validated_prompt, "default": default}
    )
    if response is None:
        try:
            return Confirm.ask(validated_prompt, default=default)
        except KeyboardInterrupt as error:
            raise InteractionCancelled("Dori interaction was cancelled.") from error
    answer = response.get("answer")
    if not isinstance(answer, bool):
        raise RuntimeError("Dori returned an invalid confirm response.")
    return answer


def choose(
    prompt: str,
    choices: Sequence[str],
    default: str | None = None,
) -> str:
    validated_prompt = _validate_prompt(prompt)
    normalized_choices = _validate_choices(choices, default)
    response = _request(
        {
            "type": "choose",
            "prompt": validated_prompt,
            "choices": normalized_choices,
            "default": default,
        }
    )
    if response is not None:
        answer = _require_string_answer(response, "choose")
        if answer not in normalized_choices:
            raise RuntimeError("Dori returned an invalid choice response.")
        return answer

    for index, choice in enumerate(normalized_choices, start=1):
        print(f"  {index}. {choice}")

    while True:
        try:
            answer = Prompt.ask(validated_prompt, default=default).strip()
        except KeyboardInterrupt as error:
            raise InteractionCancelled("Dori interaction was cancelled.") from error
        if answer.isdigit():
            selection = int(answer)
            if 1 <= selection <= len(normalized_choices):
                return normalized_choices[selection - 1]

        exact_matches = [choice for choice in normalized_choices if choice == answer]
        if len(exact_matches) == 1:
            return exact_matches[0]

        folded_matches = [
            choice
            for choice in normalized_choices
            if choice.casefold() == answer.casefold()
        ]
        if len(folded_matches) == 1:
            return folded_matches[0]

        print("Invalid choice.")


def _validate_prompt(prompt: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    return prompt


def _validate_choices(choices: Sequence[str], default: str | None) -> list[str]:
    if isinstance(choices, (str, bytes)):
        raise ValueError("choose requires a sequence of choice strings")
    if not choices:
        raise ValueError("choose requires at least one choice")

    normalized: list[str] = []
    seen: set[str] = set()
    for choice in choices:
        if not isinstance(choice, str) or not choice:
            raise ValueError("choose requires non-empty choices")
        if choice in seen:
            raise ValueError("choose requires unique choices")
        seen.add(choice)
        normalized.append(choice)

    if default is not None and default not in seen:
        raise ValueError("choose default must be one of the choices")

    return normalized


def _require_string_answer(response: dict[str, Any], request_type: str) -> str:
    answer = response.get("answer")
    if not isinstance(answer, str):
        raise RuntimeError(f"Dori returned an invalid {request_type} response.")
    return answer


def _request(payload: dict[str, Any]) -> dict[str, Any] | None:
    if os.environ.get(_DISABLED_ENV):
        raise InteractionUnavailable(
            "Interactive input is unavailable here. Use the TUI chat or run the skill directly."
        )

    request_fd_raw = os.environ.get(_REQUEST_FD_ENV)
    response_fd_raw = os.environ.get(_RESPONSE_FD_ENV)

    if bool(request_fd_raw) != bool(response_fd_raw):
        raise RuntimeError(
            "Dori interaction requires both request and response file descriptors."
        )

    if request_fd_raw is None and response_fd_raw is None:
        if sys.stdin.isatty():
            return None
        raise InteractionUnavailable(
            "Interactive input is unavailable here. Use the TUI chat or run the skill directly."
        )

    request_fd = _parse_fd(request_fd_raw, _REQUEST_FD_ENV)
    response_fd = _parse_fd(response_fd_raw, _RESPONSE_FD_ENV)

    global _next_request_id
    _next_request_id += 1
    request_id = _next_request_id

    sys.stdout.flush()
    message = {"version": _PROTOCOL_VERSION, "id": request_id, **payload}
    encoded_message = (json.dumps(message, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )

    try:
        _write_all(request_fd, encoded_message)
    except OSError as error:
        raise RuntimeError("Failed to write Dori interaction request.") from error

    raw_response = _read_line(response_fd)
    if raw_response is None:
        raise RuntimeError("Dori interaction response channel closed.")

    try:
        response = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise RuntimeError("Dori returned malformed interaction JSON.") from error

    if not isinstance(response, dict):
        raise RuntimeError("Dori returned an invalid interaction response.")
    if response.get("version") != _PROTOCOL_VERSION:
        raise RuntimeError("Dori returned an unsupported interaction protocol version.")
    if response.get("id") != request_id:
        raise RuntimeError("Dori returned a mismatched interaction response.")
    if response.get("cancelled") is True:
        raise InteractionCancelled("Dori interaction was cancelled.")
    return response


def _parse_fd(raw_value: str | None, env_name: str) -> int:
    try:
        return int(raw_value or "")
    except ValueError as error:
        raise RuntimeError(f"{env_name} must be an integer file descriptor.") from error


def _read_line(fd: int) -> str | None:
    chunks = bytearray()
    while True:
        try:
            chunk = os.read(fd, 1)
        except OSError as error:
            raise RuntimeError("Failed to read Dori interaction response.") from error

        if not chunk:
            if not chunks:
                return None
            break
        if chunk == b"\n":
            break
        chunks.extend(chunk)

    try:
        return chunks.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError("Dori returned non-UTF-8 interaction data.") from error


def _write_all(fd: int, data: bytes) -> None:
    total_written = 0
    while total_written < len(data):
        written = os.write(fd, data[total_written:])
        if written <= 0:
            raise OSError("short write")
        total_written += written
