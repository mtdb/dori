import asyncio
import json
import textwrap

import pytest

from dori.workflow import (
    InteractionRequest,
    InvalidInteractionAnswer,
    WorkflowBoundary,
    WorkflowRunner,
    normalize_answer,
    parse_request,
)


def test_normalize_confirm_answers_and_default():
    request = InteractionRequest(1, "confirm", "Continue?", default=True)

    assert normalize_answer(request, "") is True
    assert normalize_answer(request, "NO") is False


def test_normalize_choose_answers():
    request = InteractionRequest(
        2,
        "choose",
        "Type",
        choices=("feat", "fix"),
        default="fix",
    )

    assert normalize_answer(request, "1") == "feat"
    assert normalize_answer(request, "FIX") == "fix"


def test_invalid_choose_answer_raises():
    request = InteractionRequest(1, "choose", "Type", choices=("feat", "fix"))

    with pytest.raises(InvalidInteractionAnswer, match="Choose"):
        normalize_answer(request, "docs")


def test_interaction_request_rejects_invalid_combinations():
    with pytest.raises(ValueError, match="request_id"):
        InteractionRequest(0, "ask", "Prompt")
    with pytest.raises(ValueError, match="kind"):
        InteractionRequest(1, "nope", "Prompt")
    with pytest.raises(ValueError, match="prompt"):
        InteractionRequest(1, "ask", " ")
    with pytest.raises(ValueError, match="choices"):
        InteractionRequest(1, "choose", "Type", choices=())
    with pytest.raises(ValueError, match="default"):
        InteractionRequest(1, "confirm", "Continue?", default="yes")


def test_parse_request_validates_protocol_shape():
    line = json.dumps(
        {
            "version": 1,
            "id": 3,
            "type": "choose",
            "prompt": "Type",
            "choices": ["feat", "fix"],
            "default": "fix",
        }
    ).encode("utf-8")

    request = parse_request(line)

    assert request == InteractionRequest(
        3,
        "choose",
        "Type",
        choices=("feat", "fix"),
        default="fix",
    )


def test_parse_request_rejects_invalid_payloads():
    with pytest.raises(ValueError, match="JSON"):
        parse_request(b"{")
    with pytest.raises(ValueError, match="version"):
        parse_request(b'{"version":2,"id":1,"type":"ask","prompt":"Name"}')
    with pytest.raises(ValueError, match="choices"):
        parse_request(
            b'{"version":1,"id":1,"type":"choose","prompt":"Type","choices":[]}'
        )


def test_normalize_ask_and_confirm_reject_invalid_answers():
    ask_request = InteractionRequest(1, "ask", "Name")
    with pytest.raises(InvalidInteractionAnswer, match="Ask"):
        normalize_answer(ask_request, "")

    confirm_request = InteractionRequest(2, "confirm", "Continue?")
    with pytest.raises(InvalidInteractionAnswer, match="Confirm"):
        normalize_answer(confirm_request, "maybe")


def test_normalize_choose_supports_exact_and_casefold_matching():
    request = InteractionRequest(1, "choose", "Type", choices=("Feat", "fix"))

    assert normalize_answer(request, "Feat") == "Feat"
    assert normalize_answer(request, "FIX") == "fix"


def test_normalize_choose_rejects_ambiguous_casefold_match():
    request = InteractionRequest(1, "choose", "Type", choices=("Fix", "fix"))

    with pytest.raises(InvalidInteractionAnswer, match="Choose"):
        normalize_answer(request, "FIX")


def _write_script(tmp_path, source: str):
    script_path = tmp_path / "workflow_script.py"
    script_path.write_text(textwrap.dedent(source))
    return script_path


def test_runner_pauses_and_resumes_with_buffered_output(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        from dori.script import ask, confirm

        print("before name", flush=True)
        name = ask("Name")
        print(f"hello {name}", flush=True)
        approved = confirm("Continue?", default=True)
        print(f"approved={approved}", flush=True)
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(script_path, {}, cwd=tmp_path)
        try:
            first = await runner.next_boundary()
            assert first == WorkflowBoundary(
                output="before name",
                request=InteractionRequest(1, "ask", "Name"),
            )

            second = await runner.answer("Ada")
            assert second == WorkflowBoundary(
                output="hello Ada",
                request=InteractionRequest(2, "confirm", "Continue?", default=True),
            )

            final = await runner.answer("")
            assert final == WorkflowBoundary(
                output="approved=True",
                request=None,
                returncode=0,
                error=None,
            )
        finally:
            await runner.close()

    asyncio.run(scenario())


def test_runner_reports_malformed_protocol_json(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        import os

        fd = int(os.environ["DORI_INTERACTION_REQUEST_FD"])
        os.write(fd, b"{\\n")
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(script_path, {}, cwd=tmp_path)
        try:
            boundary = await runner.next_boundary()
            assert boundary.request is None
            assert boundary.returncode != 0
            assert boundary.error == "Script emitted malformed interaction JSON."
        finally:
            await runner.close()

    asyncio.run(scenario())


def test_runner_reports_non_zero_exit_with_stderr(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        import sys

        print("before fail", flush=True)
        sys.stderr.write("boom\\n")
        raise SystemExit(3)
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(script_path, {}, cwd=tmp_path)
        try:
            boundary = await runner.next_boundary()
            assert boundary == WorkflowBoundary(
                output="before fail",
                request=None,
                returncode=3,
                error="boom",
            )
        finally:
            await runner.close()

    asyncio.run(scenario())


def test_runner_reports_clean_exit_before_requesting_input(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        print("done", flush=True)
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(script_path, {}, cwd=tmp_path)
        try:
            boundary = await runner.next_boundary()
            assert boundary == WorkflowBoundary(
                output="done",
                request=None,
                returncode=0,
                error=None,
            )
        finally:
            await runner.close()

    asyncio.run(scenario())


def test_runner_cancel_reaps_process_and_returns_cancellation_boundary(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        from dori.script import ask

        print("waiting", flush=True)
        ask("Name")
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(script_path, {}, cwd=tmp_path)
        try:
            first = await runner.next_boundary()
            assert first.request == InteractionRequest(1, "ask", "Name")

            cancelled = await runner.cancel()
            assert cancelled.request is None
            assert cancelled.returncode is not None
            assert cancelled.error == "Workflow cancelled."
        finally:
            await runner.close()

    asyncio.run(scenario())


def test_runner_close_is_idempotent(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        print("done", flush=True)
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(script_path, {}, cwd=tmp_path)
        await runner.close()
        await runner.close()

    asyncio.run(scenario())


def test_invalid_answer_keeps_request_pending_without_resuming_child(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        from dori.script import choose

        print("pick", flush=True)
        choice = choose("Type", ["feat", "fix"])
        print(f"choice={choice}", flush=True)
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(script_path, {}, cwd=tmp_path)
        try:
            first = await runner.next_boundary()
            assert first.request == InteractionRequest(
                1, "choose", "Type", choices=("feat", "fix")
            )

            invalid = await runner.answer("docs")
            assert invalid.request == first.request
            assert invalid.output == ""
            assert invalid.error == "Choose responses must select a listed choice."

            final = await runner.answer("2")
            assert final == WorkflowBoundary(
                output="choice=fix",
                request=None,
                returncode=0,
                error=None,
            )
        finally:
            await runner.close()

    asyncio.run(scenario())


def test_runner_returns_error_boundary_when_interaction_is_disabled(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        from dori.script import ask

        ask("Name")
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(
            script_path, {}, cwd=tmp_path, interaction_enabled=False
        )
        try:
            boundary = await runner.next_boundary()
            assert boundary.request is None
            assert boundary.returncode != 0
            assert "Interactive input is unavailable here." in boundary.error
        finally:
            await runner.close()

    asyncio.run(scenario())
