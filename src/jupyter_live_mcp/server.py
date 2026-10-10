# Copyright (c) 2026 jlee-ax
"""Expose management tools immediately and notebook tools after selection."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import anyio
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool
from pydantic import JsonValue, ValidationError

from jupyter_live_mcp import __version__
from jupyter_live_mcp.backend import BackendConnection
from jupyter_live_mcp.controller import Controller
from jupyter_live_mcp.runtime import SessionManager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(_: Server[Controller, None]) -> AsyncGenerator[Controller]:
    """Keep the controller and backend transport inside one async lifespan."""
    async with anyio.create_task_group() as tasks:
        backend = BackendConnection(tasks)
        controller = Controller(backend, SessionManager())
        try:
            yield controller
        finally:
            # Closing the MCP transport preserves the shared Jupyter process and kernel.
            with anyio.CancelScope(shield=True):
                await backend.stop()


server = Server[Controller, None](
    "jupyter-live-mcp",
    version=__version__,
    lifespan=lifespan,
    instructions=(
        "Before starting Jupyter, discover environments and ask the user which Python to use. "
        "Only call start_session after explicit selection. Creation and package installation "
        "require the user's request. Never stop or restart a kernel unless asked. "
        "After startup, list tools again. Use MCP for all notebook edits and read cells before "
        "and after changing them. Default to code cells. Never reveal authentication tokens."
    ),
)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return the tool surface for the current selection state."""
    return server.request_context.lifespan_context.tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, JsonValue]) -> CallToolResult:
    """Return bounded operation errors through MCP without raw process output."""
    controller = server.request_context.lifespan_context
    try:
        response = await controller.call(name, arguments)
    except (RuntimeError, OSError, TimeoutError, ValidationError) as error:
        return CallToolResult(
            content=[TextContent(type="text", text=str(error))],
            isError=True,
        )
    if name in {"start_session", "stop_session"}:
        await server.request_context.session.send_tool_list_changed()
    return response


async def serve() -> None:
    """Serve the environment-selection controller over standard input/output."""
    async with stdio_server() as (reader, writer):
        await server.run(
            reader,
            writer,
            server.create_initialization_options(
                notification_options=NotificationOptions(tools_changed=True),
            ),
        )
