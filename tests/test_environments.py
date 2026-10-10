# Copyright (c) 2026 jlee-ax
"""Behavioral checks using real isolated interpreter processes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from jupyter_live_mcp.environment_models import EnvironmentOperationError
from jupyter_live_mcp.environments import (
    create_environment,
    discover_environments,
    inspect_environment,
)


def test_preserves_virtual_environment_identity_when_python_is_symlink(tmp_path: Path) -> None:
    # Given a new environment whose name is freely chosen.
    target = tmp_path / "research-custom-name"
    # When the selected interpreter creates an environment.
    info = create_environment(Path(sys.executable), target)
    # Then invocation and reported prefix both refer to that environment.
    executable = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert info.python == str(executable)
    assert Path(info.prefix).resolve() == target.resolve()
    assert info.name == target.name
    assert not info.ready
    assert any("jupyterlab" in package for package in info.missing_packages)


def test_refuses_to_overwrite_existing_environment_when_target_exists(tmp_path: Path) -> None:
    # Given an existing user directory with valuable contents.
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    _ = sentinel.write_text("original", encoding="utf-8")
    # When creation is requested at that occupied location.
    with pytest.raises(EnvironmentOperationError):
        _ = create_environment(Path(sys.executable), target)
    # Then the contents remain intact.
    assert sentinel.read_text(encoding="utf-8") == "original"


def test_discovers_project_environment_when_name_is_dotvenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real project venv, also pointed to by VIRTUAL_ENV.
    target = tmp_path / ".venv"
    _ = create_environment(Path(sys.executable), target)
    monkeypatch.setenv("VIRTUAL_ENV", str(target))
    # When known environment locations are discovered.
    environments = discover_environments(tmp_path)
    # Then duplicate registrations produce one result with the venv prefix.
    matches = [info for info in environments if Path(info.prefix).resolve() == target.resolve()]
    assert len(matches) == 1
    assert Path(matches[0].python).parent.parent == target


def test_reports_interpreter_failure_when_explicit_path_missing(tmp_path: Path) -> None:
    # Given an explicit path that does not exist.
    missing = tmp_path / "missing-python"
    # When inspection launches it, then the error identifies that invocation.
    with pytest.raises(EnvironmentOperationError) as failure:
        _ = inspect_environment(missing)
    assert failure.value.python == str(missing)


@pytest.mark.parametrize("variable", ["VIRTUAL_ENV", "CONDA_PREFIX"])
def test_discovers_activated_environment_when_outside_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    # Given an activated environment with an arbitrary name outside the project.
    target = tmp_path / "custom-selected"
    _ = create_environment(Path(sys.executable), target)
    monkeypatch.setenv(variable, str(target))
    # When the project's available environments are discovered.
    environments = discover_environments(tmp_path / "project")
    # Then the active environment is offered with its exact interpreter.
    matches = [info for info in environments if Path(info.prefix).resolve() == target.resolve()]
    assert len(matches) == 1
    assert Path(matches[0].python).parent.parent == target


@pytest.mark.parametrize(
    ("versions", "ready"),
    [(("4.4.0", "0.17.0"), True), (("5.0.0", "0.17.0"), False), (("4.4.0", "1.10.0"), False)],
)
def test_checks_package_bounds_when_metadata_is_available(
    tmp_path: Path,
    versions: tuple[str, str],
    *,
    ready: bool,
) -> None:
    # Given package metadata fixtures in a real interpreter's isolated site-packages.
    info = create_environment(Path(sys.executable), tmp_path / "metadata-fixture")
    result = subprocess.run(  # noqa: S603 - explicit local interpreter, no shell.
        [info.python, "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    packages = {
        "jupyterlab": versions[0],
        "jupyter-collaboration": "4.0.0",
        "ipykernel": "6.30.0",
        "jupyter-mcp-server": "1.1.4",
        "code-sandboxes": versions[1],
    }
    for name, version in packages.items():
        metadata = Path(result.stdout.strip()) / f"{name.replace('-', '_')}-{version}.dist-info"
        metadata.mkdir()
        _ = (metadata / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8"
        )
    # When the selected environment is inspected through its actual subprocess.
    inspected = inspect_environment(Path(info.python))
    # Then version bounds, not just distribution presence, determine readiness.
    assert inspected.ready is ready
    assert bool(inspected.missing_packages) is not ready
