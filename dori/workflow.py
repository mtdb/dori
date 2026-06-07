from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_PROTOCOL_VERSION = 1
_REQUEST_KINDS = ("ask", "confirm", "choose")
_REQUEST_FD_ENV = "DORI_INTERACTION_REQUEST_FD"
_RESPONSE_FD_ENV = "DORI_INTERACTION_RESPONSE_FD"
_DISABLED_ENV = "DORI_INTERACTION_DISABLED"
_REQUEST_ERROR = "Script emitted malformed interaction JSON."
_CANCEL_GRACE_TIMEOUT = 0.2


class InvalidInteractionAnswer(ValueError):  # noqa: N818
    pass


class _ProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class InteractionRequest:
    request_id: int
    kind: Literal["ask", "confirm", "choose"]
    prompt: str
    choices: tuple[str, ...] = ()
    default: str | bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, int) or self.request_id <= 0:
            raise ValueError("request_id must be a positive integer")
        if self.kind not in _REQUEST_KINDS:
            raise ValueError("kind must be ask, confirm, or choose")
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if not isinstance(self.choices, tuple):
            raise ValueError("choices must be a tuple")

        if self.kind == "ask":
            if self.choices:
                raise ValueError("ask requests do not accept choices")
            if self.default is not None and not isinstance(self.default, str):
                raise ValueError("default must be a string or None for ask")
            return

        if self.kind == "confirm":
            if self.choices:
                raise ValueError("confirm requests do not accept choices")
            if self.default is not None and not isinstance(self.default, bool):
                raise ValueError("default must be a boolean or None for confirm")
            return

        if not self.choices:
            raise ValueError("choices must be a non-empty tuple for choose")
        for choice in self.choices:
            if not isinstance(choice, str) or not choice:
                raise ValueError("choices must contain non-empty strings")
        if self.default is not None and self.default not in self.choices:
            raise ValueError("default must be one of the choices")


@dataclass(frozen=True)
class WorkflowBoundary:
    output: str
    request: InteractionRequest | None = None
    returncode: int | None = None
    error: str | None = None


def parse_request(line: bytes) -> InteractionRequest:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as error:
        raise ValueError("Request line must contain valid JSON.") from error

    if not isinstance(payload, dict):
        raise ValueError("Request payload must be a JSON object.")
    if payload.get("version") != _PROTOCOL_VERSION:
        raise ValueError("Request payload has an unsupported version.")

    request_id = payload.get("id")
    kind = payload.get("type")
    prompt = payload.get("prompt")
    raw_choices = payload.get("choices", [])
    default = payload.get("default")

    if raw_choices is None:
        raw_choices = []
    if not isinstance(raw_choices, list):
        raise ValueError("Request choices must be a JSON array.")

    return InteractionRequest(
        request_id=request_id,
        kind=kind,
        prompt=prompt,
        choices=tuple(raw_choices),
        default=default,
    )


def normalize_answer(request: InteractionRequest, answer: str) -> str | bool:
    if not isinstance(answer, str):
        raise InvalidInteractionAnswer("Answer must be a string.")

    normalized = answer.strip()

    if request.kind == "ask":
        if normalized:
            return normalized
        if request.default is not None:
            return request.default
        raise InvalidInteractionAnswer("Ask responses require non-empty text.")

    if request.kind == "confirm":
        if not normalized:
            if request.default is not None:
                return request.default
            raise InvalidInteractionAnswer("Confirm responses require yes or no.")
        lowered = normalized.casefold()
        if lowered in {"y", "yes"}:
            return True
        if lowered in {"n", "no"}:
            return False
        raise InvalidInteractionAnswer("Confirm responses must be yes or no.")

    if not normalized:
        if request.default is not None:
            return request.default
        raise InvalidInteractionAnswer("Choose responses must select a listed choice.")

    exact_matches = [choice for choice in request.choices if choice == normalized]
    if len(exact_matches) == 1:
        return exact_matches[0]

    folded_matches = [
        choice
        for choice in request.choices
        if choice.casefold() == normalized.casefold()
    ]
    if len(folded_matches) == 1:
        return folded_matches[0]

    if normalized.isdigit():
        selection = int(normalized)
        if 1 <= selection <= len(request.choices):
            return request.choices[selection - 1]

    raise InvalidInteractionAnswer("Choose responses must select a listed choice.")


class WorkflowRunner:
    def __init__(
        self,
        *,
        process: asyncio.subprocess.Process,
        request_read_fd: int | None,
        response_write_fd: int | None,
    ) -> None:
        self._process = process
        self._request_read_fd = request_read_fd
        self._response_write_fd = response_write_fd
        self._stdout_buffer: list[str] = []
        self._stderr_buffer: list[str] = []
        self._request_queue: asyncio.Queue[InteractionRequest | _ProtocolError] = (
            asyncio.Queue()
        )
        self._output_condition = asyncio.Condition()
        self._output_generation = 0
        self._stream_idle = {
            "stdout": self._process.stdout is None,
            "stderr": self._process.stderr is None,
        }
        self._stream_done = {
            "stdout": self._process.stdout is None,
            "stderr": self._process.stderr is None,
        }
        self._pending_request: InteractionRequest | None = None
        self._closed = False
        self._stdout_task = asyncio.create_task(
            self._drain_stream("stdout", self._process.stdout, self._stdout_buffer)
        )
        self._stderr_task = asyncio.create_task(
            self._drain_stream("stderr", self._process.stderr, self._stderr_buffer)
        )
        self._request_task = (
            asyncio.create_task(self._pump_requests())
            if self._request_read_fd is not None
            else None
        )

    @classmethod
    async def start(
        cls,
        script_path: str | Path,
        payload: object,
        cwd: str | Path,
        interaction_enabled: bool = True,
    ) -> WorkflowRunner:
        script = Path(script_path)
        working_directory = Path(cwd)
        env = os.environ.copy()
        env["PYTHONPATH"] = _build_pythonpath(env.get("PYTHONPATH"))
        payload_json = json.dumps(payload)

        request_read_fd: int | None = None
        request_write_fd: int | None = None
        response_read_fd: int | None = None
        response_write_fd: int | None = None
        pass_fds: tuple[int, ...] = ()
        created_fds: list[int] = []

        if interaction_enabled:
            request_read_fd, request_write_fd = os.pipe()
            response_read_fd, response_write_fd = os.pipe()
            created_fds.extend(
                [
                    request_read_fd,
                    request_write_fd,
                    response_read_fd,
                    response_write_fd,
                ]
            )
            env[_REQUEST_FD_ENV] = str(request_write_fd)
            env[_RESPONSE_FD_ENV] = str(response_read_fd)
            pass_fds = (request_write_fd, response_read_fd)
        else:
            env[_DISABLED_ENV] = "1"

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script),
                payload_json,
                cwd=str(working_directory),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                pass_fds=pass_fds,
            )
        except Exception:
            for fd in created_fds:
                _close_fd(fd)
            raise

        for fd in (request_write_fd, response_read_fd):
            if fd is not None:
                _close_fd(fd)

        return cls(
            process=process,
            request_read_fd=request_read_fd,
            response_write_fd=response_write_fd,
        )

    async def next_boundary(self) -> WorkflowBoundary:
        if self._pending_request is not None:
            return WorkflowBoundary(
                output="",
                request=self._pending_request,
                returncode=None,
                error=None,
            )

        if self._process.returncode is not None:
            await self._settle_output()
            return WorkflowBoundary(
                output=self._flush_output_buffer(),
                request=None,
                returncode=self._process.returncode,
                error=self._flush_error_buffer(),
            )

        queue_task = asyncio.create_task(self._request_queue.get())
        wait_task = asyncio.create_task(self._process.wait())
        done, pending = await asyncio.wait(
            {queue_task, wait_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        if queue_task in done:
            item = queue_task.result()
            if isinstance(item, _ProtocolError):
                return await self._finish_with_protocol_error(str(item))

            self._pending_request = item
            await self._settle_output()
            return WorkflowBoundary(
                output=self._flush_output_buffer(),
                request=item,
                returncode=None,
                error=None,
            )

        await self._settle_output()
        return WorkflowBoundary(
            output=self._flush_output_buffer(),
            request=None,
            returncode=wait_task.result(),
            error=self._flush_error_buffer(),
        )

    async def answer(self, value: str) -> WorkflowBoundary:
        if self._pending_request is None:
            raise RuntimeError("No interaction request is pending.")

        try:
            normalized = normalize_answer(self._pending_request, value)
        except InvalidInteractionAnswer as error:
            return WorkflowBoundary(
                output="",
                request=self._pending_request,
                returncode=None,
                error=str(error),
            )

        self._write_response(
            {
                "version": _PROTOCOL_VERSION,
                "id": self._pending_request.request_id,
                "answer": normalized,
            }
        )
        self._pending_request = None
        return await self.next_boundary()

    async def cancel(self) -> WorkflowBoundary:
        if self._pending_request is not None and self._response_write_fd is not None:
            try:
                self._write_response(
                    {
                        "version": _PROTOCOL_VERSION,
                        "id": self._pending_request.request_id,
                        "cancelled": True,
                    }
                )
                exited = await self._wait_for_process_exit(_CANCEL_GRACE_TIMEOUT)
                if exited:
                    self._pending_request = None
                    await self._settle_output()
                    return WorkflowBoundary(
                        output=self._flush_output_buffer(),
                        request=None,
                        returncode=self._process.returncode,
                        error="Workflow cancelled.",
                    )
            except OSError:
                pass

        await self._terminate_process()
        self._pending_request = None
        await self._settle_output()
        return WorkflowBoundary(
            output=self._flush_output_buffer(),
            request=None,
            returncode=self._process.returncode,
            error="Workflow cancelled.",
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._process.returncode is None:
            await self._terminate_process()

        for fd_name in ("_request_read_fd", "_response_write_fd"):
            fd = getattr(self, fd_name)
            if fd is not None:
                _close_fd(fd)
                setattr(self, fd_name, None)

        tasks = [self._stdout_task, self._stderr_task]
        if self._request_task is not None:
            tasks.append(self._request_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _pump_requests(self) -> None:
        assert self._request_read_fd is not None
        try:
            while True:
                line = await asyncio.to_thread(_read_fd_line, self._request_read_fd)
                if line is None:
                    return
                try:
                    request = parse_request(line)
                except ValueError as error:
                    await self._request_queue.put(_ProtocolError(_REQUEST_ERROR))
                    raise _ProtocolError(str(error)) from error
                await self._request_queue.put(request)
        except _ProtocolError:
            return
        except asyncio.CancelledError:
            raise
        except Exception as error:  # pragma: no cover - defensive fallback
            await self._request_queue.put(_ProtocolError(str(error)))

    async def _drain_stream(
        self,
        stream_name: str,
        stream: asyncio.StreamReader | None,
        buffer: list[str],
    ) -> None:
        if stream is None:
            return

        try:
            while True:
                await self._update_stream_state(stream_name, idle=True)
                line = await stream.readline()
                if not line:
                    await self._update_stream_state(stream_name, done=True, idle=True)
                    return
                buffer.append(line.decode("utf-8").rstrip("\n"))
                await self._update_stream_state(
                    stream_name,
                    idle=False,
                    output_generated=True,
                )
        except asyncio.CancelledError:
            raise

    async def _settle_output(self) -> None:
        async with self._output_condition:
            observed_generation = self._output_generation
            while True:
                if (
                    self._streams_are_idle()
                    and self._output_generation == observed_generation
                ):
                    return
                await self._output_condition.wait()
                observed_generation = self._output_generation

    async def _wait_for_process_exit(self, timeout: float) -> bool:
        if self._process.returncode is not None:
            return True
        try:
            await asyncio.wait_for(self._process.wait(), timeout=timeout)
        except TimeoutError:
            return False
        return True

    def _flush_output_buffer(self) -> str:
        output = "\n".join(self._stdout_buffer)
        self._stdout_buffer.clear()
        return output

    def _flush_error_buffer(self) -> str | None:
        if not self._stderr_buffer:
            return None
        error = "\n".join(self._stderr_buffer)
        self._stderr_buffer.clear()
        return error

    def _write_response(self, payload: dict[str, object]) -> None:
        if self._response_write_fd is None:
            raise OSError("Response channel is unavailable.")
        encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        _write_all(self._response_write_fd, encoded)

    async def _finish_with_protocol_error(self, message: str) -> WorkflowBoundary:
        await self._terminate_process()
        await self._settle_output()
        return WorkflowBoundary(
            output=self._flush_output_buffer(),
            request=None,
            returncode=self._process.returncode or 1,
            error=message,
        )

    async def _terminate_process(self) -> None:
        if self._process.returncode is not None:
            return

        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=_CANCEL_GRACE_TIMEOUT)
        except TimeoutError:
            self._process.kill()
            await self._process.wait()

    async def _update_stream_state(
        self,
        stream_name: str,
        *,
        idle: bool | None = None,
        done: bool | None = None,
        output_generated: bool = False,
    ) -> None:
        async with self._output_condition:
            if idle is not None:
                self._stream_idle[stream_name] = idle
            if done is not None:
                self._stream_done[stream_name] = done
            if output_generated:
                self._output_generation += 1
            self._output_condition.notify_all()

    def _streams_are_idle(self) -> bool:
        return all(
            self._stream_idle[stream_name] or self._stream_done[stream_name]
            for stream_name in self._stream_idle
        )


def _read_fd_line(fd: int) -> bytes | None:
    chunks = bytearray()
    while True:
        chunk = os.read(fd, 1)
        if not chunk:
            return None if not chunks else bytes(chunks)
        if chunk == b"\n":
            return bytes(chunks)
        chunks.extend(chunk)


def _write_all(fd: int, data: bytes) -> None:
    total_written = 0
    while total_written < len(data):
        written = os.write(fd, data[total_written:])
        if written <= 0:
            raise OSError("short write")
        total_written += written


def _close_fd(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def _build_pythonpath(existing: str | None) -> str:
    project_root = str(Path(__file__).resolve().parent.parent)
    if existing:
        return os.pathsep.join([project_root, existing])
    return project_root
