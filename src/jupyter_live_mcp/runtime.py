# Copyright (c) 2026 jlee-ax
"""Own a Jupyter process launched with the user's explicitly selected Python."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import httpx2
from anyio.abc import SocketAttribute
from anyio.to_thread import run_sync
from platformdirs import user_state_path

from jupyter_live_mcp.http_client import create_client
from jupyter_live_mcp.runtime_models import KernelInfo, SessionInfo, SessionRuntimeError

if TYPE_CHECKING:
    from jupyter_live_mcp.environment_models import EnvironmentInfo


class SessionManager:
    """Mutable owner of one process; disconnecting deliberately preserves it."""

    def __init__(self, state_root: Path | None = None) -> None:
        """Allocate controller state without starting a server."""
        self._root: Path = state_root or user_state_path("jupyter-live-mcp")
        self._info: SessionInfo | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._token: str = ""
        self._state: Path | None = None
        self._lock: anyio.Lock = anyio.Lock()

    @property
    def info(self) -> SessionInfo | None:
        """Return nonsecret identity, if startup has completed."""
        return self._info

    @property
    def token(self) -> str:
        """Return the credential for internal MCP transport only."""
        return self._token

    async def start(self, project: Path, environment: EnvironmentInfo) -> SessionInfo:
        """Start on explicit selection, or reuse the same owned live session."""
        async with self._lock:
            project = await run_sync(lambda: project.resolve(strict=True))
            if not project.is_dir() or not environment.ready:
                reason = "Select an existing project and a ready Python environment."
                raise SessionRuntimeError(reason)
            if self._info is not None:
                if self._info.project != str(project) or self._info.python != environment.python:
                    reason = "Stop the active session explicitly before changing selection."
                    raise SessionRuntimeError(reason)
                if self._process is None or self._process.poll() is not None:
                    reason = "The owned Jupyter process exited. Stop it before restarting."
                    raise SessionRuntimeError(reason)
                return self._info
            self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._state = Path(tempfile.mkdtemp(prefix="session-", dir=self._root))
            self._token = secrets.token_urlsafe(32)
            success = False
            try:
                self._prepare(project, environment)
                for _attempt in range(3):
                    async with await anyio.create_tcp_listener(
                        local_host="127.0.0.1",
                        local_port=0,
                    ) as reservation:
                        port = reservation.extra(SocketAttribute.local_port)  # noqa: S610
                    self._launch(environment, port)
                    url = f"http://127.0.0.1:{port}"
                    if await self._ready(url):
                        break
                    await self._terminate()
                else:
                    reason = "Jupyter exited during startup after three attempts."
                    raise SessionRuntimeError(reason)
                async with create_client(url, self._token) as client:
                    response = await client.post("/api/kernels", json={"name": "jupyter-live"})
                    _ = response.raise_for_status()
                    kernel = KernelInfo.model_validate_json(response.content)
                    response = await client.get(f"/api/kernels/{kernel.id}")
                    _ = response.raise_for_status()
                    inspected = KernelInfo.model_validate_json(response.content)
                    if inspected.name != "jupyter-live" or inspected.id != kernel.id:
                        reason = "Jupyter did not activate the selected kernelspec."
                        raise SessionRuntimeError(reason)
                self._info = SessionInfo(
                    project=str(project),
                    python=environment.python,
                    prefix=environment.prefix,
                    url=url,
                    token_file=str(self._state / "token"),
                    kernel_id=kernel.id,
                    kernel_name=kernel.name,
                    state_dir=str(self._state),
                )
                _ = (self._state / "session.json").write_text(
                    self._info.model_dump_json(),
                    encoding="utf-8",
                )
                success = True
                return self._info
            finally:
                if not success:
                    with anyio.CancelScope(shield=True):
                        await self._terminate()
                        self._clear()

    def _prepare(self, project: Path, environment: EnvironmentInfo) -> None:
        state = self._state
        if state is None:
            reason = "Session state has not been allocated."
            raise SessionRuntimeError(reason)
        with open(state / "token", "x", encoding="utf-8", opener=_private_opener) as token_file:
            _ = token_file.write(self._token)
        kernels = state / "data" / "kernels" / "jupyter-live"
        kernels.mkdir(parents=True, mode=0o700)
        _ = (kernels / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [
                        environment.python,
                        "-m",
                        "ipykernel_launcher",
                        "-f",
                        "{connection_file}",
                    ],
                    "display_name": f"Python ({environment.name})",
                    "language": "python",
                }
            ),
            encoding="utf-8",
        )
        (state / "runtime").mkdir(mode=0o700)
        (state / "config").mkdir(mode=0o700)
        # Read authentication from a private file; never include it in argv or logs.
        config = (
            "from pathlib import Path\n"
            f"c.IdentityProvider.token = Path({str(state / 'token')!r}).read_text()\n"
            "c.ServerApp.ip = '127.0.0.1'\n"
            "c.ServerApp.open_browser = False\n"
            "c.ServerApp.port_retries = 0\n"
            "c.ServerApp.allow_remote_access = False\n"
            "c.ServerApp.use_redirect_file = False\n"
            "c.ServerApp.jpserver_extensions = {'jupyterlab': True, "
            "'jupyter_server_ydoc': True, 'jupyter_server_nbmodel': True, "
            "'jupyter_server_fileid': True, 'jupyter_mcp_server': False}\n"
            f"c.ServerApp.root_dir = {str(project)!r}\n"
            "c.KernelSpecManager.ensure_native_kernel = False\n"
            f"c.KernelSpecManager.kernel_dirs = {[str(state / 'data' / 'kernels')]!r}\n"
            "c.KernelSpecManager.allowed_kernelspecs = {'jupyter-live'}\n"
            "c.MappingKernelManager.default_kernel_name = 'jupyter-live'\n"
        )
        _ = (state / "config" / "jupyter_config.py").write_text(config, encoding="utf-8")

    def _launch(self, environment: EnvironmentInfo, port: int) -> None:
        state = self._state
        if state is None:
            reason = "Session state has not been allocated."
            raise SessionRuntimeError(reason)
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("JUPYTER_", "IPYTHON", "PYTHON"))
            and key not in {"CONDA_PREFIX", "CONDA_DEFAULT_ENV", "VIRTUAL_ENV"}
        }
        env.update(
            {
                "JUPYTER_CONFIG_DIR": str(state / "config"),
                "JUPYTER_DATA_DIR": str(state / "data"),
                "JUPYTER_RUNTIME_DIR": str(state / "runtime"),
                "IPYTHONDIR": str(state / "ipython"),
                "PATH": str(Path(environment.python).parent) + os.pathsep + env.get("PATH", ""),
            }
        )
        # Popen ownership outlives MCP disconnect; only explicit stop terminates it.
        self._process = subprocess.Popen(  # noqa: S603
            [
                environment.python,
                "-I",
                "-m",
                "jupyterlab",
                "--collaborative",
                f"--config={state / 'config' / 'jupyter_config.py'}",
                f"--ServerApp.port={port}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=state,
            start_new_session=True,
        )

    async def _ready(self, url: str) -> bool:
        with anyio.fail_after(45):
            async with create_client(url, self._token) as client:
                while self._process is not None and self._process.poll() is None:
                    try:
                        response = await client.get("/api/status")
                    except httpx2.TransportError:
                        await anyio.sleep(0.1)
                        continue
                    if response.status_code == HTTPStatus.OK:
                        return True
                    await anyio.sleep(0.1)
        return False

    async def _terminate(self) -> None:
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    _ = await run_sync(lambda: process.wait(timeout=10))
                except subprocess.TimeoutExpired:
                    process.kill()
                    _ = await run_sync(lambda: process.wait(timeout=5))
            self._process = None

    def _clear(self) -> None:
        if self._state is not None:
            (self._state / "token").unlink(missing_ok=True)
        self._token = ""
        self._info = None

    async def stop(self) -> None:
        """Stop only this manager's owned process, with bounded escalation."""
        async with self._lock:
            with anyio.CancelScope(shield=True):
                await self._terminate()
                self._clear()


def _private_opener(path: str, flags: int) -> int:
    return os.open(path, flags, 0o600)
