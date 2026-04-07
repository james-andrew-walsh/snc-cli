"""equipment commands."""

from __future__ import annotations

from typing import Optional

import typer

from snc_cli.client import get_supabase_client
from snc_cli.output import abort, output

app = typer.Typer(name="equipment", help="Manage equipment.")


@app.command("list")
def list_equipment(
    business_unit: Optional[str] = typer.Option(None, "--business-unit", help="Filter by business unit UUID"),
    active: Optional[str] = typer.Option(None, "--active", help="Filter by active status (true/false)"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List equipment, optionally filtered."""
    q = get_supabase_client().table("Equipment").select("*")
    if business_unit:
        q = q.eq("businessUnitId", business_unit)
    if active is not None:
        q = q.eq("isActive", active.lower() == "true")
    resp = q.execute()
    output(resp.data, human, title="Equipment")


@app.command("get")
def get_equipment(
    id: str = typer.Option(..., "--id", help="Equipment UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Get a single equipment record by ID."""
    resp = get_supabase_client().table("Equipment").select("*").eq("id", id).execute()
    if not resp.data:
        abort(f"Equipment ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Equipment")


@app.command("create")
def create_equipment(
    business_unit: str = typer.Option(..., "--business-unit", help="Business unit UUID"),
    code: str = typer.Option(..., "--code", help="Equipment code"),
    make: str = typer.Option(..., "--make", help="Equipment make"),
    model: str = typer.Option(..., "--model", help="Equipment model"),
    year: int = typer.Option(..., "--year", help="Equipment year"),
    description: Optional[str] = typer.Option(None, "--description", help="Description"),
    serial_number: Optional[str] = typer.Option(None, "--serial-number", help="Serial number"),
    gps_device_tag: Optional[str] = typer.Option(None, "--gps-device-tag", help="GPS device tag"),
    is_rental: bool = typer.Option(False, "--is-rental", help="Mark as rental"),
    is_active: bool = typer.Option(True, "--is-active", help="Mark as active"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Create a new equipment record."""
    payload: dict = {
        "businessUnitId": business_unit,
        "code": code,
        "make": make,
        "model": model,
        "year": year,
        "isRental": is_rental,
        "isActive": is_active,
    }
    if description is not None:
        payload["description"] = description
    if serial_number is not None:
        payload["serialNumber"] = serial_number
    if gps_device_tag is not None:
        payload["gpsDeviceTag"] = gps_device_tag

    resp = get_supabase_client().table("Equipment").upsert(payload, on_conflict="code,businessUnitId").execute()
    if not resp.data:
        abort("Failed to create equipment.")
    output(resp.data[0], human, title="Equipment Created")


@app.command("update")
def update_equipment(
    id: str = typer.Option(..., "--id", help="Equipment UUID"),
    is_active: Optional[str] = typer.Option(None, "--is-active", help="Set active (true/false)"),
    is_rental: Optional[str] = typer.Option(None, "--is-rental", help="Set rental (true/false)"),
    status: Optional[str] = typer.Option(None, "--status", help="Set dispatcher status (Available, In Use, Down)"),
    description: Optional[str] = typer.Option(None, "--description", help="Description"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Update an equipment record."""
    updates: dict = {}
    if is_active is not None:
        updates["isActive"] = is_active.lower() == "true"
    if is_rental is not None:
        updates["isRental"] = is_rental.lower() == "true"
    if status is not None:
        if status not in ("Available", "In Use", "Down"):
            abort("--status must be one of: Available, In Use, Down")
        updates["status"] = status
    if description is not None:
        updates["description"] = description

    if not updates:
        abort("No update fields provided. Use --is-active, --is-rental, --status, or --description.")

    resp = get_supabase_client().table("Equipment").update(updates).eq("id", id).execute()
    if not resp.data:
        abort(f"Equipment ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Equipment Updated")


@app.command("transfer")
def transfer_equipment(
    id: str = typer.Option(..., "--id", help="Equipment UUID"),
    to_business_unit: str = typer.Option(..., "--to-business-unit", help="Target business unit UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Transfer equipment to another business unit."""
    resp = (
        get_supabase_client()
        .table("Equipment")
        .update({"businessUnitId": to_business_unit})
        .eq("id", id)
        .execute()
    )
    if not resp.data:
        abort(f"Equipment ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Equipment Transferred")
