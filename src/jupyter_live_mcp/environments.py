# Copyright (c) 2026 jlee-ax
"""Discover, inspect and explicitly prepare user-selected Python environments."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from packaging.requirements import Requirement
from packaging.version import InvalidVersion, Version
from pydantic import ValidationError

from jupyter_live_mcp.environment_models import (
    CondaEnvironments,
    EnvironmentInfo,
    EnvironmentOperationError,
    InterpreterProbe,
)

REQUIRED_PACKAGES: Final = (
    "jupyterlab>=4,<5",
    "jupyter-collaboration>=4,<5",
    "ipykernel>=6,<8",
    "jupyter-mcp-server==1.1.4",
    "code-sandboxes==0.17.0",
)
MINIMUM_PYTHON: Final = Version("3.11")
MAX_CANDIDATES: Final = 32
PROBE: Final = """
import importlib.metadata
import json
import sys
packages = {}
for name in sys.argv[1:]:
    try:
        packages[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        packages[name] = None
print(json.dumps({"prefix": sys.prefix,
                  "version": ".".join(map(str, sys.version_info[:3])),
                  "packages": packages}))
"""


def _run(command: list[str], timeout: int) -> str:
    """Run an explicit executable with bounded duration and isolated input."""
    try:
        result = subprocess.run(  # noqa: S603 - argv, never a shell; user selects executable.
            command,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EnvironmentOperationError(
            command[0], f"operation failed ({type(exc).__name__})"
        ) from exc
    return result.stdout


def inspect_environment(python: Path) -> EnvironmentInfo:
    """Inspect a Python path without resolving away a virtualenv's symlink."""
    invocation = python.expanduser().absolute()
    requirements = tuple(Requirement(value) for value in REQUIRED_PACKAGES)
    raw = _run([str(invocation), "-I", "-c", PROBE, *(r.name for r in requirements)], 10)
    try:
        probe = InterpreterProbe.model_validate_json(raw)
        missing: list[str] = []
        if Version(probe.version) < MINIMUM_PYTHON:
            missing.append(f"Python>=3.11 (found {probe.version})")
        for requirement in requirements:
            installed = probe.packages.get(requirement.name)
            if installed is None:
                missing.append(str(requirement))
            elif Version(installed) not in requirement.specifier:
                missing.append(f"{requirement} (found {installed})")
    except (ValidationError, InvalidVersion) as exc:
        raise EnvironmentOperationError(str(invocation), "invalid interpreter metadata") from exc
    return EnvironmentInfo(
        python=str(invocation),
        prefix=probe.prefix,
        version=probe.version,
        name=Path(probe.prefix).name,
        missing_packages=tuple(missing),
        ready=not missing,
    )


def _environment_python(prefix: Path) -> Path:
    """Select the interpreter layout for the current operating system."""
    if os.name == "nt" and (prefix / "python.exe").is_file():
        return prefix / "python.exe"
    return prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def discover_environments(project: Path) -> list[EnvironmentInfo]:
    """Inspect bounded known locations; do not walk unrelated directories."""
    candidates = [_environment_python(project / name) for name in (".venv", "venv")]
    candidates.extend(
        _environment_python(Path(prefix))
        for key in ("VIRTUAL_ENV", "CONDA_PREFIX")
        if (prefix := os.environ.get(key))
    )
    candidates.append(Path(sys.executable))
    if path_python := shutil.which("python"):
        candidates.append(Path(path_python))
    if conda := shutil.which("conda"):
        try:
            conda_envs = CondaEnvironments.model_validate_json(
                _run([conda, "env", "list", "--json"], 10)
            )
        except (EnvironmentOperationError, ValidationError):
            conda_envs = CondaEnvironments(envs=())
        candidates.extend(_environment_python(Path(p)) for p in conda_envs.envs[:MAX_CANDIDATES])
    environments: list[EnvironmentInfo] = []
    seen_paths: set[str] = set()
    seen_prefixes: set[str] = set()
    for candidate in candidates[:MAX_CANDIDATES]:
        path = str(candidate.expanduser().absolute())
        if path in seen_paths or not candidate.is_file():
            continue
        seen_paths.add(path)
        try:
            info = inspect_environment(Path(path))
        except EnvironmentOperationError:
            continue  # Stale registrations must not hide other usable environments.
        if info.prefix not in seen_prefixes:
            environments.append(info)
            seen_prefixes.add(info.prefix)
    return environments


def create_environment(base_python: Path, target: Path) -> EnvironmentInfo:
    """Create a new venv only when explicitly requested, never over an existing path."""
    base = inspect_environment(base_python)
    if Version(base.version) < MINIMUM_PYTHON:
        raise EnvironmentOperationError(
            base.python, f"Python>=3.11 required (found {base.version})"
        )
    destination = target.expanduser().absolute()
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise EnvironmentOperationError(
            str(destination), "cannot create target; choose a new writable path"
        ) from exc
    _ = _run([base.python, "-I", "-m", "venv", str(destination)], 120)
    return inspect_environment(_environment_python(destination))


def install_dependencies(python: Path) -> EnvironmentInfo:
    """Install required packages into the explicitly selected interpreter using uv."""
    info = inspect_environment(python)
    if Version(info.version) < MINIMUM_PYTHON:
        raise EnvironmentOperationError(
            info.python, f"Python>=3.11 required (found {info.version})"
        )
    uv = shutil.which("uv")
    if uv is None:
        raise EnvironmentOperationError(info.python, "uv is required to install dependencies")
    _ = _run([uv, "pip", "install", "--python", info.python, *REQUIRED_PACKAGES], 600)
    return inspect_environment(Path(info.python))
