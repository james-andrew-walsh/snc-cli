"""telemetry commands."""

from __future__ import annotations

from typing import Optional

import typer

from snc_cli.client import get_supabase_client
from snc_cli.output import abort, output

app = typer.Typer(name="telemetry", help="Update equipment telemetry.")


@app.command("update")
def update_telemetry(
    gps_device_tag: str = typer.Option(..., "--gps-device-tag", help="GPS device tag to look up equipment"),
    hour_meter: Optional[int] = typer.Option(None, "--hour-meter", help="New hour-meter reading"),
    odometer: Optional[int] = typer.Option(None, "--odometer", help="New odometer reading"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Update telemetry (hourMeter / odometer) for equipment identified by GPS device tag."""
    updates: dict = {}
    if hour_meter is not None:
        updates["hourMeter"] = hour_meter
    if odometer is not None:
        updates["odometer"] = odometer

    if not updates:
        abort("Provide at least one of --hour-meter or --odometer.")

    resp = (
        get_supabase_client()
        .table("Equipment")
        .update(updates)
        .eq("gpsDeviceTag", gps_device_tag)
        .execute()
    )
    if not resp.data:
        abort(
            f"No equipment found with gpsDeviceTag '{gps_device_tag}'. "
            "Ensure the tag exists on an equipment record."
        )
    output(resp.data[0], human, title="Telemetry Updated")
