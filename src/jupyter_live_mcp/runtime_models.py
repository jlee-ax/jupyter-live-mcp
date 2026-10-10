# Copyright (c) 2026 jlee-ax
"""Typed Jupyter session metadata; authentication secrets are never serialized."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class SessionInfo(BaseModel):
    """Public identity of a selected-environment Jupyter session."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    project: str
    python: str
    prefix: str
    url: str
    token_file: str
    kernel_id: str
    kernel_name: str
    state_dir: str


class KernelInfo(BaseModel):
    """Parse the relevant fields of Jupyter's kernel REST response."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    id: str
    name: str


class SessionRuntimeError(RuntimeError):
    """An actionable runtime failure without subprocess secrets."""

    def __init__(self, reason: str) -> None:
        """Carry only a safe, caller-facing failure reason."""
        self.reason: str = reason
        super().__init__(reason)
