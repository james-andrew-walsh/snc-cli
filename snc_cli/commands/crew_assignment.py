"""crew-assignment commands."""

from __future__ import annotations

from typing import Optional

import typer
from postgrest.exceptions import APIError

from snc_cli.auth import load_credentials
from snc_cli.client import get_supabase_client, handle_api_error
from snc_cli.output import abort, output

app = typer.Typer(name="crew-assignment", help="Manage crew assignments to jobs.")


@app.command("list")
def list_assignments(
    job: Optional[str] = typer.Option(None, "--job", help="Filter by job UUID"),
    employee: Optional[str] = typer.Option(None, "--employee", help="Filter by employee UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List crew assignments, optionally filtered by job or employee."""
    q = get_supabase_client().table("CrewAssignment").select("*")
    if job:
        q = q.eq("jobId", job)
    if employee:
        q = q.eq("employeeId", employee)
    resp = q.execute()
    output(resp.data, human, title="Crew Assignments")


@app.command("get")
def get_assignment(
    id: str = typer.Option(..., "--id", help="Crew Assignment UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Get a single crew assignment by ID."""
    resp = get_supabase_client().table("CrewAssignment").select("*").eq("id", id).execute()
    if not resp.data:
        abort(f"Crew Assignment ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Crew Assignment")


@app.command("assign")
def assign_crew(
    job: str = typer.Option(..., "--job", help="Job UUID"),
    employee: str = typer.Option(..., "--employee", help="Employee UUID"),
    start: str = typer.Option(..., "--start", help="Start date (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", help="End date (YYYY-MM-DD, optional)"),
    role: Optional[str] = typer.Option(None, "--role", help="Role on this job (e.g. Operator, Crew Lead)"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Notes"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Assign an employee to a job."""
    payload: dict = {
        "jobId": job,
        "employeeId": employee,
        "startDate": start,
    }
    if end:
        payload["endDate"] = end
    if role:
        payload["role"] = role
    if notes:
        payload["notes"] = notes

    try:
        resp = get_supabase_client().table("CrewAssignment").insert(payload).execute()
    except APIError as e:
        creds = load_credentials()
        handle_api_error(e, email=creds.get("email") if creds else None, role=creds.get("role") if creds else None)
    if not resp.data:
        abort("Failed to create crew assignment.")
    output(resp.data[0], human, title="Crew Assignment Created")


@app.command("remove")
def remove_assignment(
    id: str = typer.Option(..., "--id", help="Crew Assignment UUID to remove"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Remove a crew assignment."""
    try:
        resp = get_supabase_client().table("CrewAssignment").delete().eq("id", id).execute()
    except APIError as e:
        creds = load_credentials()
        handle_api_error(e, email=creds.get("email") if creds else None, role=creds.get("role") if creds else None)
    if not resp.data:
        abort(f"Crew Assignment ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Crew Assignment Removed")
