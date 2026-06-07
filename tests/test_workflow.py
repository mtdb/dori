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


def test_normalize_ask_uses_default_for_empty_input():
    request = InteractionRequest(1, "ask", "Name", default="Ada")

    assert normalize_answer(request, "") == "Ada"


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


def test_normalize_choose_uses_default_for_empty_input():
    request = InteractionRequest(
        2,
        "choose",
        "Type",
        choices=("feat", "fix"),
        default="fix",
    )

    assert normalize_answer(request, "") == "fix"


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


def test_runner_waits_for_stdout_quiescence_before_request_boundary(monkeypatch):
    request = InteractionRequest(1, "ask", "Name")
    ready = asyncio.Event()
    stopped = asyncio.Event()

    class FakeProcess:
        def __init__(self):
            self.stdout = object()
            self.stderr = object()
            self.returncode = None

        async def wait(self):
            await stopped.wait()
            return self.returncode or 0

        def terminate(self):
            self.returncode = -15
            stopped.set()

        def kill(self):
            self.returncode = -9
            stopped.set()

    async def scenario():
        async def fake_drain(self, stream_name, stream, buffer):
            if stream_name == "stdout":
                await self._update_stream_state(stream_name, idle=False)
                ready.set()
                await asyncio.sleep(0.08)
                buffer.append("before name")
                await self._update_stream_state(
                    stream_name,
                    idle=False,
                    output_generated=True,
                )
                await self._update_stream_state(stream_name, idle=True, done=True)
                return
            await self._update_stream_state(stream_name, idle=True, done=True)

        monkeypatch.setattr(WorkflowRunner, "_drain_stream", fake_drain)
        process = FakeProcess()
        runner = WorkflowRunner(
            process=process,
            request_read_fd=None,
            response_write_fd=None,
        )
        try:
            await ready.wait()
            await runner._request_queue.put(request)
            boundary = await runner.next_boundary()
            assert boundary == WorkflowBoundary(
                output="before name",
                request=request,
                returncode=None,
                error=None,
            )
        finally:
            await runner.close()

    asyncio.run(scenario())


def test_runner_waits_for_stdout_quiescence_before_exit_boundary(monkeypatch):
    stopped = asyncio.Event()

    class FakeProcess:
        def __init__(self):
            self.stdout = object()
            self.stderr = object()
            self.returncode = None

        async def wait(self):
            if self.returncode is None:
                self.returncode = 0
            stopped.set()
            return self.returncode

        def terminate(self):
            self.returncode = -15
            stopped.set()

        def kill(self):
            self.returncode = -9
            stopped.set()

    async def scenario():
        async def fake_drain(self, stream_name, stream, buffer):
            if stream_name == "stdout":
                await self._update_stream_state(stream_name, idle=False)
                await asyncio.sleep(0.08)
                buffer.append("done")
                await self._update_stream_state(
                    stream_name,
                    idle=False,
                    output_generated=True,
                )
                await self._update_stream_state(stream_name, idle=True, done=True)
                return
            await self._update_stream_state(stream_name, idle=True, done=True)

        monkeypatch.setattr(WorkflowRunner, "_drain_stream", fake_drain)
        process = FakeProcess()
        runner = WorkflowRunner(
            process=process,
            request_read_fd=None,
            response_write_fd=None,
        )
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


def test_runner_closes_all_pipe_fds_when_startup_fails(monkeypatch, tmp_path):
    closed_fds = []
    pipe_pairs = [(11, 12), (13, 14)]

    async def fail_spawn(*args, **kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr("dori.workflow.os.pipe", lambda: pipe_pairs.pop(0))
    monkeypatch.setattr("dori.workflow._close_fd", closed_fds.append)
    monkeypatch.setattr("dori.workflow.asyncio.create_subprocess_exec", fail_spawn)

    async def scenario():
        with pytest.raises(OSError, match="spawn failed"):
            await WorkflowRunner.start(tmp_path / "missing.py", {}, cwd=tmp_path)

    asyncio.run(scenario())

    assert closed_fds == [11, 12, 13, 14]


def test_runner_forwards_payload_as_json_argv(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        import json
        import sys

        payload = json.loads(sys.argv[1])
        print(f"{payload['skill']} cli={payload['cli']} args={payload['args']}", flush=True)
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(
            script_path,
            {"skill": "commit", "cli": True, "args": ["--amend"]},
            cwd=tmp_path,
        )
        try:
            boundary = await runner.next_boundary()
            assert boundary == WorkflowBoundary(
                output="commit cli=True args=['--amend']",
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


def test_runner_cancel_allows_graceful_script_cleanup(tmp_path):
    script_path = _write_script(
        tmp_path,
        """
        from dori.script import InteractionCancelled, ask

        print("waiting", flush=True)
        try:
            ask("Name")
        except InteractionCancelled:
            print("cancelled cleanly", flush=True)
        """,
    )

    async def scenario():
        runner = await WorkflowRunner.start(script_path, {}, cwd=tmp_path)
        try:
            first = await runner.next_boundary()
            assert first.request == InteractionRequest(1, "ask", "Name")

            cancelled = await runner.cancel()
            assert cancelled == WorkflowBoundary(
                output="cancelled cleanly",
                request=None,
                returncode=0,
                error="Workflow cancelled.",
            )
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
