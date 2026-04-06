"""dispatch commands."""

from __future__ import annotations

from datetime import date
from typing import Optional

import typer

from snc_cli.client import get_client
from snc_cli.output import abort, output

app = typer.Typer(name="dispatch", help="Manage dispatch events.")


@app.command("list")
def list_dispatches(
    equipment_id: Optional[str] = typer.Option(None, "--equipment-id", help="Filter by equipment UUID"),
    operator_id: Optional[str] = typer.Option(None, "--operator-id", help="Filter by operator/employee UUID"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="Filter by destination job UUID"),
    from_date: Optional[str] = typer.Option(None, "--from-date", help="Filter dispatches from this date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, "--to-date", help="Filter dispatches up to this date (YYYY-MM-DD)"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List dispatch events, optionally filtered."""
    q = get_client().table("DispatchEvent").select("*")
    if equipment_id:
        q = q.eq("equipmentId", equipment_id)
    if operator_id:
        q = q.eq("operatorId", operator_id)
    if job_id:
        q = q.eq("jobId", job_id)
    if from_date:
        q = q.gte("startDate", from_date)
    if to_date:
        q = q.lte("startDate", to_date)
    resp = q.order("startDate", desc=False).execute()
    output(resp.data, human, title="Dispatch Events")


@app.command("get")
def get_dispatch(
    id: str = typer.Option(..., "--id", help="Dispatch Event UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Get a single dispatch event by ID."""
    resp = get_client().table("DispatchEvent").select("*").eq("id", id).execute()
    if not resp.data:
        abort(f"Dispatch Event ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Dispatch Event")


@app.command("schedule")
def schedule_dispatch(
    equipment: str = typer.Option(..., "--equipment", help="Equipment UUID to dispatch"),
    job: Optional[str] = typer.Option(None, "--job", help="Destination Job UUID"),
    location: Optional[str] = typer.Option(None, "--location", help="Destination Location UUID"),
    operator: str = typer.Option(..., "--operator", help="Employee UUID of the assigned operator"),
    start: str = typer.Option(..., "--start", help="Start date (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", help="End date (YYYY-MM-DD, optional)"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Dispatch notes"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Schedule a new dispatch event."""
    if not job and not location:
        abort("Must provide --job or --location as destination.")

    payload: dict = {
        "equipmentId": equipment,
        "operatorId": operator,
        "startDate": start,
    }
    if job:
        payload["jobId"] = job
    if location:
        payload["locationId"] = location
    if end:
        payload["endDate"] = end
    if notes:
        payload["notes"] = notes

    resp = get_client().table("DispatchEvent").insert(payload).execute()
    if not resp.data:
        abort("Failed to schedule dispatch.")
    output(resp.data[0], human, title="Dispatch Scheduled")


@app.command("cancel")
def cancel_dispatch(
    id: str = typer.Option(..., "--id", help="Dispatch Event UUID to cancel"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Cancel (delete) a dispatch event."""
    resp = get_client().table("DispatchEvent").delete().eq("id", id).execute()
    if not resp.data:
        abort(f"Dispatch Event ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Dispatch Cancelled")
