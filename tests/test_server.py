# Copyright (c) 2026 jlee-ax
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from anyio import fail_after, run_process
from anyio.to_thread import run_sync
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from jupyter_live_mcp.environments import inspect_environment, install_dependencies

if TYPE_CHECKING:
    from mcp.types import CallToolResult


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _parameters(project: Path) -> StdioServerParameters:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "jupyter_live_mcp", "serve"],
        cwd=str(project),
        env=env,
    )


def _text(response: CallToolResult) -> str:
    return "\n".join(item.text for item in response.content if isinstance(item, TextContent))


@pytest.mark.anyio
async def test_notebook_operations_require_environment_selection(tmp_path: Path) -> None:
    # Given a newly connected controller with no environment selection.
    async with (
        stdio_client(_parameters(tmp_path)) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        _ = await session.initialize()
        # When the client attempts to execute notebook code before selecting Python.
        blocked = await session.call_tool("execute_code", {"code": "print(1)"})
        # Then the controller blocks execution and advertises only management tools.
        assert blocked.isError
        assert "start_session" in _text(blocked)
        tools = (await session.list_tools()).tools
        assert "discover_environments" in {tool.name for tool in tools}
        assert "execute_code" not in {tool.name for tool in tools}


@pytest.mark.anyio
@pytest.mark.integration
@pytest.mark.parametrize("environment_name", ["teaching-env", "research-env"])
async def test_selected_environment_executes_notebook_cells(
    tmp_path: Path,
    environment_name: str,
) -> None:
    # Given a real venv whose name differs from the legacy fixed name.
    prefix = tmp_path / environment_name
    with fail_after(120):
        _ = await run_process(
            [sys.executable, "-m", "venv", "--system-site-packages", str(prefix)],
            check=True,
        )
    python = prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    inspected = await run_sync(inspect_environment, python)
    if not inspected.ready:
        _ = await run_sync(install_dependencies, python)
    async with (
        stdio_client(_parameters(tmp_path)) as (reader, writer),
        ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=120)) as session,
    ):
        _ = await session.initialize()
        started = await session.call_tool(
            "start_session",
            {
                "project": str(tmp_path),
                "python_path": str(python),
            },
        )
        assert not started.isError, _text(started)
        try:
            tools = (await session.list_tools()).tools
            assert "execute_cell" in {tool.name for tool in tools}
            files = await session.call_tool("list_files", {"path": ""})
            assert not files.isError, _text(files)
            _ = await session.call_tool("list_notebooks", {})
            created = await session.call_tool(
                "use_notebook",
                {
                    "notebook_name": "qa",
                    "notebook_path": "qa.ipynb",
                    "mode": "create",
                },
            )
            assert not created.isError, _text(created)
            _ = await session.call_tool("read_notebook", {"notebook_name": "qa"})
            inserted = await session.call_tool(
                "insert_cell",
                {
                    "notebook_name": "qa",
                    "cell_index": 0,
                    "cell_type": "code",
                    "cell_source": """# 선택한 가상환경에서 실행되는지 확인합니다.
import sys
print(sys.prefix)
print(6 * 7)""",
                },
            )
            assert not inserted.isError, _text(inserted)
            _ = await session.call_tool("read_cell", {"notebook_name": "qa", "cell_index": 0})
            # When a cell executes through the published MCP tool surface.
            executed = await session.call_tool(
                "execute_cell",
                {
                    "notebook_name": "qa",
                    "cell_index": 0,
                },
            )
            # Then the output proves the selected venv and computed result.
            assert not executed.isError, _text(executed)
            output = await session.call_tool(
                "read_cell",
                {
                    "notebook_name": "qa",
                    "cell_index": 0,
                },
            )
            assert str(prefix) in _text(output)
            assert "42" in _text(output)
            assert "token=" not in _text(started)
        finally:
            stopped = await session.call_tool("stop_session", {})
            assert not stopped.isError, _text(stopped)
