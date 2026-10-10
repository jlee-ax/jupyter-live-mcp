# Copyright (c) 2026 jlee-ax
"""Enforce environment selection before forwarding notebook operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

import anyio
from anyio.to_thread import run_sync
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import BaseModel, JsonValue

from jupyter_live_mcp.environments import (
    create_environment,
    discover_environments,
    inspect_environment,
    install_dependencies,
)
from jupyter_live_mcp.notebooks import create_notebook
from jupyter_live_mcp.tool_models import (
    CreateInput,
    EmptyInput,
    NotebookInput,
    ProjectInput,
    PythonInput,
    StartInput,
)

if TYPE_CHECKING:
    from jupyter_live_mcp.backend import BackendConnection
    from jupyter_live_mcp.runtime import SessionManager

NOTEBOOK_TOOLS: Final = frozenset(
    {
        "list_files",
        "list_kernels",
        "list_notebooks",
        "use_notebook",
        "unuse_notebook",
        "read_notebook",
        "insert_cell",
        "overwrite_cell_source",
        "edit_cell_source",
        "execute_cell",
        "insert_execute_code_cell",
        "read_cell",
        "delete_cell",
        "clear_cell_output",
        "move_cell",
        "execute_code",
        "restart_notebook",
    }
)


def result(value: BaseModel | list[BaseModel] | dict[str, JsonValue]) -> CallToolResult:
    """Serialize typed management results without credentials."""
    if isinstance(value, BaseModel):
        data = value.model_dump_json()
    elif isinstance(value, list):
        data = "[" + ",".join(item.model_dump_json() for item in value) + "]"
    else:
        data = json.dumps(value)
    return CallToolResult(content=[TextContent(type="text", text=data)])


def management_tools() -> list[Tool]:
    """Publish only selection and lifecycle actions before Jupyter starts."""
    definitions = [
        (
            "discover_environments",
            "Find Python environments; then ask the user to select one.",
            ProjectInput,
            True,
        ),
        (
            "inspect_environment",
            "Check the user's selected Python and required packages.",
            PythonInput,
            True,
        ),
        (
            "create_environment",
            "Create a venv only when the user requests a new environment.",
            CreateInput,
            False,
        ),
        (
            "install_dependencies",
            "Install required Jupyter packages only after user authorization.",
            PythonInput,
            False,
        ),
        (
            "start_session",
            "Start Jupyter using the Python explicitly selected by the user.",
            StartInput,
            False,
        ),
        (
            "session_info",
            "Read the selected environment and nonsecret browser session details.",
            EmptyInput,
            True,
        ),
        ("stop_session", "Stop this session only on explicit user request.", EmptyInput, False),
    ]
    return [
        Tool(
            name=name,
            description=description,
            inputSchema=model.model_json_schema(),
            annotations=ToolAnnotations(readOnlyHint=readonly, openWorldHint=False),
        )
        for name, description, model, readonly in definitions
    ]


class Controller:
    """Own selection and backend state; serialize lifecycle changes and tool calls."""

    def __init__(self, backend: BackendConnection, runtime: SessionManager) -> None:
        """Bind the backend and owned runtime to a serialized controller."""
        self.backend: BackendConnection = backend
        self.runtime: SessionManager = runtime
        self._lock: anyio.Lock = anyio.Lock()

    def tools(self) -> list[Tool]:
        """Expose notebook operations only when a backend is connected."""
        return management_tools() + [
            tool for tool in self.backend.tools if tool.name in NOTEBOOK_TOOLS
        ]

    async def call(self, name: str, args: dict[str, JsonValue]) -> CallToolResult:
        """Validate and serialize operations across the shared session."""
        async with self._lock:
            return await self._dispatch(name, args)

    async def _dispatch(self, name: str, args: dict[str, JsonValue]) -> CallToolResult:
        if name in {
            "discover_environments",
            "inspect_environment",
            "create_environment",
            "install_dependencies",
        }:
            return await self._environment(name, args)
        match name:
            case "start_session":
                return await self._start(StartInput.model_validate(args))
            case "session_info":
                _ = EmptyInput.model_validate(args)
                info = self.runtime.info
                if info is not None:
                    return result(info)
                return result({"status": "selection_required"})
            case "stop_session":
                _ = EmptyInput.model_validate(args)
                await self.backend.stop()
                await self.runtime.stop()
                return result({"status": "stopped"})
            case _:
                return await self._notebook(name, args)

    async def _environment(self, name: str, args: dict[str, JsonValue]) -> CallToolResult:
        match name:
            case "discover_environments":
                request = ProjectInput.model_validate(args)
                environments = await run_sync(
                    discover_environments,
                    Path(request.project),
                )
                return result(list(environments))
            case "inspect_environment":
                request = PythonInput.model_validate(args)
                return result(
                    await run_sync(
                        inspect_environment,
                        Path(request.python_path),
                    )
                )
            case "create_environment":
                request = CreateInput.model_validate(args)
                return result(
                    await run_sync(
                        create_environment,
                        Path(request.base_python),
                        Path(request.target_path),
                    )
                )
            case "install_dependencies":
                request = PythonInput.model_validate(args)
                if self.runtime.info is not None:
                    message = "Install dependencies before starting a session."
                    raise RuntimeError(message)
                return result(
                    await run_sync(
                        install_dependencies,
                        Path(request.python_path),
                    )
                )
            case _:
                message = "Unknown environment operation."
                raise RuntimeError(message)

    async def _start(self, request: StartInput) -> CallToolResult:
        environment = await run_sync(
            inspect_environment,
            Path(request.python_path),
        )
        info = await self.runtime.start(Path(request.project), environment)
        success = False
        try:
            await self.backend.start(info, self.runtime.token)
            await self._verify_kernel()
            success = True
        finally:
            if not success:
                with anyio.CancelScope(shield=True):
                    try:
                        await self.backend.stop()
                    finally:
                        await self.runtime.stop()
        return result(info)

    async def _verify_kernel(self) -> None:
        info = self.runtime.info
        if info is None:
            message = "No selected runtime is available."
            raise RuntimeError(message)
        code = f"""assert __import__('os').path.samefile(
    __import__('sys').executable, {info.python!r})
assert __import__('os').path.realpath(__import__('sys').prefix) == (
    __import__('os').path.realpath({info.prefix!r}))
print('JUPYTER_LIVE_KERNEL_VERIFIED')
"""
        identity = await self.backend.call(
            "execute_code",
            {
                "code": code,
                "kernel_id": info.kernel_id,
            },
        )
        identity_text = "\n".join(
            item.text for item in identity.content if isinstance(item, TextContent)
        )
        if identity.isError or "JUPYTER_LIVE_KERNEL_VERIFIED" not in identity_text:
            message = "Kernel identity verification failed; session was stopped."
            raise RuntimeError(message)

    async def _notebook(self, name: str, args: dict[str, JsonValue]) -> CallToolResult:
        info = self.runtime.info
        if info is None or name not in NOTEBOOK_TOOLS:
            message = "Select an environment and call start_session before notebook operations."
            raise RuntimeError(message)
        forwarded = args.copy()
        if name in {"use_notebook", "execute_code"}:
            requested_kernel = forwarded.get("kernel_id")
            if requested_kernel is not None and requested_kernel != info.kernel_id:
                message = "The requested kernel differs from the selected environment's kernel."
                raise RuntimeError(message)
            forwarded["kernel_id"] = info.kernel_id
        if name == "use_notebook":
            request = NotebookInput.model_validate(forwarded)
            if request.mode == "create":
                await create_notebook(self.runtime, request.notebook_path)
                forwarded["mode"] = "connect"
        return await self.backend.call(name, forwarded)
