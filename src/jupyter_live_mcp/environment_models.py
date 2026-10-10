# Copyright (c) 2026 jlee-ax
"""Validated environment inspection results."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class EnvironmentInfo(BaseModel):
    """An interpreter invocation and its readiness for Jupyter Live."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    python: str
    prefix: str
    version: str
    name: str
    missing_packages: tuple[str, ...]
    ready: bool


class InterpreterProbe(BaseModel):
    """Parse the isolated interpreter's JSON response."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    prefix: str
    version: str
    packages: dict[str, str | None]


class CondaEnvironments(BaseModel):
    """Parse conda's machine-readable environment list."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    envs: tuple[str, ...]


class EnvironmentOperationError(RuntimeError):
    """Report a failed environment operation without leaking process output."""

    python: str
    reason: str

    def __init__(self, python: str, reason: str) -> None:
        """Keep actionable interpreter context with the failure."""
        self.python = python
        self.reason = reason
        super().__init__(f"{python}: {reason}")
