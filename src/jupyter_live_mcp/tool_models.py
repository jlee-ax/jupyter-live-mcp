# Copyright (c) 2026 jlee-ax
"""Validate management tool inputs before they reach process operations."""

from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class ToolInput(BaseModel):
    """Reject unknown input fields at the management boundary."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class EmptyInput(ToolInput):
    """No arguments are accepted for lifecycle queries."""


class ProjectInput(ToolInput):
    """Locate the project whose environments should be discovered."""

    project: str = str(Path.cwd())


class PythonInput(ToolInput):
    """Require an explicit interpreter invocation path."""

    python_path: str


class CreateInput(ToolInput):
    """Describe an explicitly requested new virtual environment."""

    base_python: str
    target_path: str


class StartInput(PythonInput):
    """Bind a user's interpreter choice to a project."""

    project: str = str(Path.cwd())


class NotebookInput(ToolInput):
    """Bind notebook activation to the selected kernel, with empty creation by default."""

    notebook_name: str
    notebook_path: str
    mode: Literal["connect", "create"] = "connect"
    kernel_id: str | None = None
