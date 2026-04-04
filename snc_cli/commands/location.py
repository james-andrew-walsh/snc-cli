"""location commands."""

from __future__ import annotations

from typing import Optional

import typer

from snc_cli.client import get_client
from snc_cli.output import abort, output

app = typer.Typer(name="location", help="Manage locations.")


@app.command("list")
def list_locations(
    business_unit: Optional[str] = typer.Option(None, "--business-unit", help="Filter by business unit UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List locations, optionally filtered by business unit."""
    q = get_client().table("Location").select("*")
    if business_unit:
        q = q.eq("businessUnitId", business_unit)
    resp = q.execute()
    output(resp.data, human, title="Locations")


@app.command("get")
def get_location(
    id: str = typer.Option(..., "--id", help="Location UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Get a single location by ID."""
    resp = get_client().table("Location").select("*").eq("id", id).execute()
    if not resp.data:
        abort(f"Location ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Location")


@app.command("create")
def create_location(
    business_unit: str = typer.Option(..., "--business-unit", help="Business unit UUID"),
    code: str = typer.Option(..., "--code", help="Location code"),
    description: str = typer.Option(..., "--description", help="Location description"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Create a new location."""
    payload = {
        "businessUnitId": business_unit,
        "code": code,
        "description": description,
    }
    resp = get_client().table("Location").upsert(payload, on_conflict="code,businessUnitId").execute()
    if not resp.data:
        abort("Failed to create location.")
    output(resp.data[0], human, title="Location Created")
