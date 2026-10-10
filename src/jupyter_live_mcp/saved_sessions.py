# Copyright (c) 2026 jlee-ax
"""Read and explicitly stop preserved sessions using authenticated loopback requests."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import anyio
import httpx2
from anyio.to_thread import run_sync
from platformdirs import user_state_path

from jupyter_live_mcp.http_client import create_client
from jupyter_live_mcp.runtime_models import SessionInfo, SessionRuntimeError


def saved_sessions() -> list[SessionInfo]:
    """List nonsecret metadata for sessions preserved after MCP disconnect."""
    root = user_state_path("jupyter-live-mcp")
    return [
        SessionInfo.model_validate_json(path.read_text(encoding="utf-8"))
        for path in root.glob("session-*/session.json")
        if (path.parent / "token").is_file()
    ]


def _load(state_dir: Path) -> tuple[SessionInfo, str]:
    state = state_dir.resolve(strict=True)
    info = SessionInfo.model_validate_json((state / "session.json").read_text(encoding="utf-8"))
    address = urlsplit(info.url)
    if (
        address.scheme != "http"
        or address.hostname != "127.0.0.1"
        or address.username is not None
        or address.password is not None
        or address.query
        or address.fragment
        or address.path not in {"", "/"}
    ):
        message = "Saved session address must be an unauthenticated loopback URL."
        raise SessionRuntimeError(message)
    if (
        Path(info.state_dir).resolve() != state
        or Path(info.token_file).resolve() != state / "token"
    ):
        message = "Saved session paths do not match the selected state directory."
        raise SessionRuntimeError(message)
    return info, (state / "token").read_text(encoding="utf-8")


async def stop_saved_session(state_dir: Path) -> None:
    """Stop an explicitly chosen saved session without terminating unrelated processes."""
    info, token = await run_sync(_load, state_dir)
    async with create_client(info.url, token) as client:
        response = await client.post("/api/shutdown")
        _ = response.raise_for_status()
        with anyio.fail_after(15):
            while True:
                try:
                    _ = await client.get("/api/status")
                except httpx2.ConnectError:
                    break
                except (httpx2.ReadError, httpx2.RemoteProtocolError):
                    await anyio.sleep(0.1)
                    continue
                await anyio.sleep(0.1)
    await run_sync(lambda: (state_dir / "token").unlink(missing_ok=True))
