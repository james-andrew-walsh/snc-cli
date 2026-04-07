"""job commands."""

from __future__ import annotations

import json
from typing import Optional

import typer
from postgrest.exceptions import APIError

from snc_cli.auth import load_credentials
from snc_cli.client import get_supabase_client, handle_api_error
from snc_cli.output import abort, output

app = typer.Typer(name="job", help="Manage jobs.")


@app.command("list")
def list_jobs(
    business_unit: Optional[str] = typer.Option(None, "--business-unit", help="Filter by business unit UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List jobs, optionally filtered by business unit."""
    q = get_supabase_client().table("Job").select("*")
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
    resp = get_supabase_client().table("Job").select("*").eq("id", id).execute()
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
    try:
        resp = get_supabase_client().table("Job").upsert(payload, on_conflict="code,businessUnitId").execute()
    except APIError as e:
        creds = load_credentials()
        handle_api_error(e, email=creds.get("email") if creds else None, role=creds.get("role") if creds else None)
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

    try:
        resp = get_supabase_client().table("Job").update(updates).eq("id", id).execute()
    except APIError as e:
        creds = load_credentials()
        handle_api_error(e, email=creds.get("email") if creds else None, role=creds.get("role") if creds else None)
    if not resp.data:
        abort(f"Job ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Job Updated")


@app.command("delete")
def delete_job(
    id: str = typer.Option(..., "--id", help="Job UUID"),
    force: bool = typer.Option(False, "--force", help="Delete dependent records and the job"),
) -> None:
    """Delete a job. Checks for dependent records unless --force is used."""
    client = get_supabase_client()

    dispatches = client.table("DispatchEvent").select("*").eq("jobId", id).execute()
    crews = client.table("CrewAssignment").select("*").eq("jobId", id).execute()
    dispatch_count = len(dispatches.data)
    crew_count = len(crews.data)

    if not force and (dispatch_count > 0 or crew_count > 0):
        typer.echo(
            f"Error: Cannot delete job — {dispatch_count} dispatch event(s) "
            f"and {crew_count} crew assignment(s) reference this job.\n"
            "Use --force to cancel all dependent records and delete the job."
        )
        raise SystemExit(1)

    try:
        if dispatch_count > 0:
            client.table("DispatchEvent").delete().eq("jobId", id).execute()
        if crew_count > 0:
            client.table("CrewAssignment").delete().eq("jobId", id).execute()

        resp = client.table("Job").delete().eq("id", id).execute()
    except APIError as e:
        creds = load_credentials()
        handle_api_error(e, email=creds.get("email") if creds else None, role=creds.get("role") if creds else None)
    if not resp.data:
        abort(f"Job ID {id} not found. Ensure the ID is a valid UUID.")

    result = {
        "deleted": True,
        "id": id,
        "dispatches_removed": dispatch_count,
        "crew_removed": crew_count,
    }
    typer.echo(json.dumps(result, indent=2))
