# Copyright (c) 2026 jlee-ax
"""Keep the selected environment's MCP connection in one owning async task."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from anyio.to_thread import run_sync
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

if TYPE_CHECKING:
    from anyio.abc import TaskGroup, TaskStatus
    from mcp.types import CallToolResult, Tool
    from pydantic import JsonValue

    from jupyter_live_mcp.runtime_models import SessionInfo


class BackendConnection:
    """Mutable connection state; its transport remains owned by the lifespan task."""

    def __init__(self, tasks: TaskGroup) -> None:
        """Use the server lifespan's task group for transport ownership."""
        self._tasks: TaskGroup = tasks
        self._session: ClientSession | None = None
        self._stop: anyio.Event = anyio.Event()
        self._closed: anyio.Event = anyio.Event()
        self.tools: list[Tool] = []

    async def start(self, info: SessionInfo, token: str) -> None:
        """Start the backend with the selected interpreter and private credentials."""
        if self._session is not None:
            return
        self._stop = anyio.Event()
        self._closed = anyio.Event()
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PYTHON", "JUPYTER_", "CONDA_", "VIRTUAL_ENV"))
        }
        env.update(
            {
                "PATH": os.pathsep.join([str(Path(info.python).parent), env.get("PATH", "")]),
                "JUPYTER_URL": info.url,
                "JUPYTER_TOKEN": token,
                "RUNTIME_URL": info.url,
                "RUNTIME_TOKEN": token,
                "DOCUMENT_URL": info.url,
                "DOCUMENT_TOKEN": token,
                "START_NEW_RUNTIME": "false",
                "JUPYTERLAB": "true",
                "OPEN_NOTEBOOK_IN_UI": "false",
                "ALLOW_IMG_OUTPUT": "true",
            }
        )
        params = StdioServerParameters(
            command=info.python,
            args=["-I", "-m", "jupyter_mcp_server", "start", "--transport", "stdio"],
            env=env,
            cwd=info.project,
        )
        await self._tasks.start(self._run, params)

    async def _run(
        self,
        params: StdioServerParameters,
        *,
        task_status: TaskStatus[None],
    ) -> None:
        try:
            # Backend logs may contain credentials; keep them outside protocol output.
            with await run_sync(lambda: Path(os.devnull).open("w", encoding="utf-8")) as errors:
                async with (
                    stdio_client(params, errlog=errors) as (reader, writer),
                    ClientSession(
                        reader, writer, read_timeout_seconds=timedelta(seconds=120)
                    ) as session,
                ):
                    _ = await session.initialize()
                    self.tools = (await session.list_tools()).tools
                    self._session = session
                    task_status.started()
                    await self._stop.wait()
        finally:
            self._session = None
            self.tools = []
            self._closed.set()

    async def call(self, name: str, arguments: dict[str, JsonValue]) -> CallToolResult:
        """Forward one tool call while preserving the upstream content blocks."""
        session = self._session
        if session is None:
            message = "Select an environment and call start_session first."
            raise RuntimeError(message)
        return await session.call_tool(name, arguments)

    async def stop(self) -> None:
        """Close the backend transport without stopping the Jupyter kernel."""
        if self._session is not None:
            self._stop.set()
            await self._closed.wait()
