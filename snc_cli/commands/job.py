"""job commands."""

from __future__ import annotations

from typing import Optional

import typer

from snc_cli.client import get_client
from snc_cli.output import abort, output

app = typer.Typer(name="job", help="Manage jobs.")


@app.command("list")
def list_jobs(
    business_unit: Optional[str] = typer.Option(None, "--business-unit", help="Filter by business unit UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List jobs, optionally filtered by business unit."""
    q = get_client().table("Job").select("*")
    if business_unit:
        q = q.eq("businessUnitId", business_unit)
    resp = q.execute()
    output(resp.data, human, title="Jobs")


@app.command("get")
def get_job(
    id: str = typer.Option(..., "--id", help="Job UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Get a single job by ID."""
    resp = get_client().table("Job").select("*").eq("id", id).execute()
    if not resp.data:
        abort(f"Job ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Job")


@app.command("create")
def create_job(
    business_unit: str = typer.Option(..., "--business-unit", help="Business unit UUID"),
    code: str = typer.Option(..., "--code", help="Job code"),
    description: str = typer.Option(..., "--description", help="Job description"),
    location: str = typer.Option(..., "--location", help="UUID of the Location where this job takes place. Required."),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Create a new job."""
    payload = {
        "businessUnitId": business_unit,
        "code": code,
        "description": description,
        "locationId": location,
    }
    resp = get_client().table("Job").upsert(payload, on_conflict="code,businessUnitId").execute()
    if not resp.data:
        abort("Failed to create job.")
    output(resp.data[0], human, title="Job Created")


@app.command("update")
def update_job(
    id: str = typer.Option(..., "--id", help="Job UUID"),
    description: Optional[str] = typer.Option(None, "--description", help="Job description"),
    location: Optional[str] = typer.Option(None, "--location", help="Location UUID (job site)"),
    code: Optional[str] = typer.Option(None, "--code", help="Job code"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Update a job record."""
    updates: dict = {}
    if description is not None:
        updates["description"] = description
    if location is not None:
        updates["locationId"] = location
    if code is not None:
        updates["code"] = code

    if not updates:
        abort("No update fields provided. Use --description, --location, or --code.")

    resp = get_client().table("Job").update(updates).eq("id", id).execute()
    if not resp.data:
        abort(f"Job ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Job Updated")
