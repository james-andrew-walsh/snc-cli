"""business-unit commands."""

from __future__ import annotations

from typing import Optional

import typer

from snc_cli.client import get_client
from snc_cli.output import abort, output

app = typer.Typer(name="business-unit", help="Manage business units.")


@app.command("list")
def list_business_units(
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List all business units."""
    resp = get_client().table("BusinessUnit").select("*").execute()
    output(resp.data, human, title="Business Units")


@app.command("get")
def get_business_unit(
    id: str = typer.Option(..., "--id", help="Business unit UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Get a single business unit by ID."""
    resp = get_client().table("BusinessUnit").select("*").eq("id", id).execute()
    if not resp.data:
        abort(f"Business unit ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Business Unit")


@app.command("create")
def create_business_unit(
    code: str = typer.Option(..., "--code", help="Business unit code"),
    description: str = typer.Option(..., "--description", help="Business unit description"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Create a new business unit."""
    payload = {
        "code": code,
        "description": description,
    }
    resp = get_client().table("BusinessUnit").upsert(payload, on_conflict="code").execute()
    if not resp.data:
        abort("Failed to create business unit.")
    output(resp.data[0], human, title="Business Unit Created")
