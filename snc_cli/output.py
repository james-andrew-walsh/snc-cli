"""Shared output helpers."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer


def print_json(data: Any) -> None:
    """Pretty-print *data* as JSON to stdout."""
    typer.echo(json.dumps(data, indent=2, default=str))


def print_human(data: dict | list[dict], title: str = "") -> None:
    """Print a human-readable table of *data*."""
    if isinstance(data, dict):
        data = [data]
    if not data:
        typer.echo("No records found.")
        return
    if title:
        typer.echo(f"\n{title}")
        typer.echo("-" * len(title))
    keys = list(data[0].keys())
    for row in data:
        for k in keys:
            typer.echo(f"  {k}: {row.get(k)}")
        typer.echo()


def output(data: Any, human: bool, title: str = "") -> None:
    """Route to JSON or human output."""
    if human:
        print_human(data, title=title)
    else:
        print_json(data)


def abort(message: str) -> None:
    """Print an error and exit 1."""
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)
