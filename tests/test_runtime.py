# Copyright (c) 2026 jlee-ax
"""Observe selected-environment startup and ownership through real Jupyter HTTP."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import anyio
import pytest

from jupyter_live_mcp.environment_models import EnvironmentInfo
from jupyter_live_mcp.http_client import create_client
from jupyter_live_mcp.runtime import SessionManager
from jupyter_live_mcp.runtime_models import SessionRuntimeError


def environment(python: str, *, ready: bool = True) -> EnvironmentInfo:
    return EnvironmentInfo(
        python=python,
        prefix=str(Path(python).parent.parent),
        version="3.12",
        name="arbitrary-user-environment",
        missing_packages=() if ready else ("jupyterlab",),
        ready=ready,
    )


def test_start_rejects_unready_environment_without_creating_state(tmp_path: Path) -> None:
    # Given an environment which needs installation and an unused state directory.
    root = tmp_path / "state"
    manager = SessionManager(root)

    # When startup is requested without runtime dependencies.
    with pytest.raises(SessionRuntimeError):
        _ = anyio.run(manager.start, tmp_path, environment("unavailable-python", ready=False))

    # Then nothing launches or writes credentials.
    assert manager.info is None
    assert manager.token == ""
    assert not root.exists()


def test_start_failure_removes_credentials_and_allows_retry(tmp_path: Path) -> None:
    # Given a selected executable that is absent.
    manager = SessionManager(tmp_path / "state")

    # When process creation fails.
    with pytest.raises(FileNotFoundError):
        _ = anyio.run(manager.start, tmp_path, environment(str(tmp_path / "missing-python")))

    # Then cleanup removes authentication and process ownership.
    assert manager.info is None
    assert manager.token == ""
    assert not list((tmp_path / "state").glob("session-*/token"))


@pytest.mark.integration
def test_real_session_auth_isolation_and_explicit_switch(tmp_path: Path) -> None:
    python = os.environ.get("JUPYTER_LIVE_TEST_PYTHON")
    if python is None:
        pytest.skip("Set JUPYTER_LIVE_TEST_PYTHON to run real Jupyter lifecycle verification.")

    async def scenario() -> None:
        # Given a user-selected interpreter and two projects with independent state.
        first_project, second_project = tmp_path / "first", tmp_path / "second"
        first_project.mkdir()
        second_project.mkdir()
        selected = environment(python)
        manager = SessionManager(tmp_path / "state")
        observer = SessionManager(tmp_path / "other-controller")

        # When the selected runtime is started and an active selection change is requested.
        try:
            first = await manager.start(first_project, selected)
            assert await manager.start(first_project, selected) == first
            with pytest.raises(SessionRuntimeError):
                _ = await manager.start(second_project, selected)
            alternate = selected.model_copy(update={"python": str(tmp_path / "another-python")})
            with pytest.raises(SessionRuntimeError):
                _ = await manager.start(first_project, alternate)
            await observer.stop()

            # Then the owned kernel remains reachable, authenticated, and privately configured.
            async with create_client(first.url, manager.token) as client:
                response = await client.get(f"/api/kernels/{first.kernel_id}")
                assert response.status_code == 200
                specs = await client.get("/api/kernelspecs")
                assert specs.status_code == 200
                assert selected.python in specs.text
                assert '"default": "jupyter-live"' in specs.text
                content = await client.put(
                    "/api/contents/collaboration-test.txt",
                    json={"type": "file", "format": "text", "content": "collaboration probe"},
                )
                assert content.status_code == 201
                collaboration = await client.put(
                    "/api/collaboration/session/collaboration-test.txt",
                    json={"format": "text", "type": "file"},
                )
                assert collaboration.status_code == 201
            async with create_client(first.url, "invalid-token") as client:
                response = await client.get("/api/kernels")
                assert response.status_code == 403
            token_file = anyio.Path(first.token_file)
            if os.name == "posix":
                assert stat.S_IMODE((await token_file.stat()).st_mode) == 0o600
            assert manager.token not in first.model_dump_json()
            assert manager.token not in (Path(first.state_dir) / "session.json").read_text()
            assert (
                manager.token
                not in (Path(first.state_dir) / "config" / "jupyter_config.py").read_text()
            )

            # When the user explicitly stops, a different project can start.
            await manager.stop()
            assert not await token_file.exists()
            second = await manager.start(second_project, selected)

            # Then this is a new session bound to the second project.
            assert second.project == str(second_project.resolve())
            assert second.kernel_id != first.kernel_id
            assert second.state_dir != first.state_dir
        finally:
            await manager.stop()

    anyio.run(scenario)
