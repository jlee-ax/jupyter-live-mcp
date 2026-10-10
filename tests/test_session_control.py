# Copyright (c) 2026 jlee-ax
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent
from typing_extensions import override

from jupyter_live_mcp.backend import BackendConnection
from jupyter_live_mcp.controller import Controller
from jupyter_live_mcp.runtime import SessionManager
from jupyter_live_mcp.runtime_models import SessionInfo, SessionRuntimeError
from jupyter_live_mcp.saved_sessions import stop_saved_session

if TYPE_CHECKING:
    from mcp.types import CallToolResult


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FailingBackend(BackendConnection):
    @override
    async def start(self, info: SessionInfo, token: str) -> None:
        message = "test transport initialization failure"
        raise ExceptionGroup(message, [RuntimeError(message)])


@pytest.mark.anyio
@pytest.mark.integration
async def test_transport_failure_cleans_owned_jupyter(tmp_path: Path) -> None:
    # Given a real runtime and a failing transport initialization boundary.
    async with anyio.create_task_group() as tasks:
        runtime = SessionManager(tmp_path / "state")
        controller = Controller(FailingBackend(tasks), runtime)
        # When backend initialization fails after Jupyter has started.
        with pytest.raises(ExceptionGroup):
            _ = await controller.call(
                "start_session",
                {
                    "python_path": sys.executable,
                    "project": str(tmp_path),
                },
            )
        # Then its kernel and credentials are cleaned rather than left unmanaged.
        assert runtime.info is None
        assert runtime.token == ""
        assert not list((tmp_path / "state").glob("session-*/token"))


def _content(response: CallToolResult) -> str:
    return "\n".join(item.text for item in response.content if isinstance(item, TextContent))


@pytest.mark.anyio
@pytest.mark.integration
async def test_saved_session_can_stop_after_controller_disconnect(tmp_path: Path) -> None:
    # Given a session which must keep its kernel after the Codex transport closes.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jupyter_live_mcp", "serve"],
        cwd=str(tmp_path),
        env=env,
    )
    async with (
        stdio_client(params) as (reader, writer),
        ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=120)) as session,
    ):
        _ = await session.initialize()
        started = await session.call_tool(
            "start_session",
            {
                "python_path": sys.executable,
                "project": str(tmp_path),
            },
        )
        assert not started.isError, _content(started)
        info = SessionInfo.model_validate_json(_content(started))
    # When the user explicitly stops the retained session using its saved identity.
    await stop_saved_session(Path(info.state_dir))
    # Then the credential is removed and the saved session cannot be reused for shutdown.
    assert not await anyio.Path(info.token_file).exists()


@pytest.mark.anyio
async def test_saved_stop_rejects_nonlocal_address_before_reading_token(tmp_path: Path) -> None:
    # Given tampered metadata pointing outside the user's computer.
    info = SessionInfo(
        project=str(tmp_path),
        python=sys.executable,
        prefix=sys.prefix,
        url="http://example.com:8888",
        token_file=str(tmp_path / "token"),
        kernel_id="fixture",
        kernel_name="jupyter-live",
        state_dir=str(tmp_path),
    )
    _ = (tmp_path / "session.json").write_text(info.model_dump_json(), encoding="utf-8")
    # When stopping a saved session is requested.
    with pytest.raises(SessionRuntimeError):
        await stop_saved_session(tmp_path)
    # Then it fails without contacting the remote host or needing any credential.
    assert not (tmp_path / "token").exists()
