# Copyright (c) 2026 jlee-ax
"""Create empty notebooks through Jupyter's API before the MCP backend activates them."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import quote

from jupyter_live_mcp.http_client import create_client
from jupyter_live_mcp.runtime_models import SessionRuntimeError

if TYPE_CHECKING:
    from jupyter_live_mcp.runtime import SessionManager


async def create_notebook(runtime: SessionManager, relative_path: str) -> None:
    """Create an empty notebook without upstream's automatic Markdown seed or overwrites."""
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".ipynb":
        message = "New notebook must be a relative .ipynb path within the selected project."
        raise SessionRuntimeError(message)
    info = runtime.info
    if info is None:
        message = "Select an environment before creating a notebook."
        raise SessionRuntimeError(message)
    endpoint = "/api/contents/" + quote(relative_path, safe="/")
    async with create_client(info.url, runtime.token) as client:
        existing = await client.get(endpoint)
        if existing.status_code != HTTPStatus.NOT_FOUND:
            _ = existing.raise_for_status()
            message = "Notebook path already exists. Use connect instead of create."
            raise SessionRuntimeError(message)
        response = await client.put(
            endpoint,
            json={
                "type": "notebook",
                "format": "json",
                "content": {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5},
            },
        )
        _ = response.raise_for_status()
