# Copyright (c) 2026 jlee-ax
"""Command-line entry points for installation checks and the MCP transport."""

from pathlib import Path
from typing import Annotated

import anyio
import typer

from jupyter_live_mcp.environments import discover_environments, inspect_environment
from jupyter_live_mcp.saved_sessions import saved_sessions, stop_saved_session
from jupyter_live_mcp.server import serve as serve_mcp

app = typer.Typer(add_completion=False)


@app.command()
def serve() -> None:
    """Start the selection controller without launching Jupyter."""
    anyio.run(serve_mcp)


@app.command()
def environments(
    project: Annotated[str, typer.Option(help="Project to inspect for .venv.")] = ".",
) -> None:
    """List discoverable environments as JSON."""
    values = discover_environments(Path(project))
    typer.echo("[" + ",".join(item.model_dump_json() for item in values) + "]")


@app.command()
def inspect(python: Annotated[Path, typer.Argument(help="Selected Python executable.")]) -> None:
    """Report required packages and interpreter identity as JSON."""
    typer.echo(inspect_environment(python).model_dump_json())


@app.command()
def sessions() -> None:
    """List preserved sessions without disclosing their authentication tokens."""
    typer.echo("[" + ",".join(item.model_dump_json() for item in saved_sessions()) + "]")


@app.command()
def stop(
    state_dir: Annotated[Path, typer.Option(help="Exact state_dir from sessions output.")],
) -> None:
    """Explicitly shut down one preserved Jupyter session."""
    anyio.run(stop_saved_session, state_dir)
    typer.echo("Session stopped.")
