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

@app.command("list")
def list_telemetry(
    provider: Optional[str] = typer.Option(None, "--provider", help="Filter by provider (e.g. jdlink, e360)"),
    code: Optional[str] = typer.Option(None, "--code", help="Filter by equipment code"),
    stale: Optional[bool] = typer.Option(None, "--stale", help="Filter by stale location status"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List latest telemetry for equipment, using the get_latest_telematics RPC."""
    resp = get_supabase_client().rpc("get_latest_telematics").execute()
    data = resp.data
    
    if provider:
        data = [d for d in data if str(d.get("providerKey") or d.get("providerkey")).lower() == provider.lower()]
    if code:
        data = [d for d in data if str(d.get("equipmentCode") or d.get("equipmentcode")).lower() == code.lower()]
    if stale is not None:
        data = [d for d in data if (d.get("isLocationStale") if "isLocationStale" in d else d.get("islocationstale")) == stale]
        
    output(data, human, title="Latest Telemetry")

@app.command("compare")
def compare_telemetry(
    code: str = typer.Option(..., "--code", help="Equipment code to compare across providers"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Compare the latest telemetry for a specific equipment across all providers.
    Bypasses the RPC to show raw underlying snapshot availability."""
    
    # Get latest snapshot per provider directly from table
    resp = get_supabase_client().table("TelematicsSnapshot").select("*").eq("equipmentCode", code).order("snapshotAt", desc=True).execute()
    data = resp.data
    
    if not data:
        abort(f"No telemetry found for equipment '{code}'")
        
    providers = {}
    for d in data:
        p = d.get("providerKey") or "unknown"
        if p not in providers:
            providers[p] = d
            
    output(list(providers.values()), human, title=f"Provider Comparison for '{code}'")

