"""sync commands — pull data from external providers into Supabase."""

from __future__ import annotations

import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
import typer
from supabase import create_client

app = typer.Typer(name="sync", help="Sync external data sources.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JDLINK_TOKEN_URL = (
    "https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token"
)
AEMP_BASE_PROD = "https://partneraemp.deere.com"
AEMP_BASE_SANDBOX = "https://sandboxaemp.deere.com"

STALE_THRESHOLD_SECONDS = 4 * 60 * 60  # 4 hours

INSERT_BATCH_SIZE = 500

# ISO 15143-3 XML namespace
AEMP_NS = "http://standards.iso.org/iso/15143/-3"
NS_MAP = {"ns": AEMP_NS}


# ---------------------------------------------------------------------------
# JDLink Authentication
# ---------------------------------------------------------------------------


def _get_jdlink_token(app_id: str, secret: str, refresh_token: str) -> str:
    """Obtain an OAuth2 access token from John Deere using a refresh token."""
    resp = httpx.post(
        JDLINK_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": app_id,
            "client_secret": secret,
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"JDLink auth failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(1)
    token = resp.json().get("access_token")
    if not token:
        print("JDLink auth response missing access_token", file=sys.stderr)
        sys.exit(1)
    return token


# ---------------------------------------------------------------------------
# AEMP Fleet Fetching (paginated XML)
# ---------------------------------------------------------------------------


def _fetch_fleet_pages(token: str, base_url: str) -> list[str]:
    """Fetch all pages of AEMP Fleet XML."""
    pages: list[str] = []
    page_number = 1

    while True:
        if page_number > 1:
            time.sleep(1.5)

        url = f"{base_url}/Fleet/{page_number}"
        resp = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/xml",
            },
            timeout=60,
        )

        if resp.status_code == 404 and page_number > 1:
            break
        if resp.status_code != 200:
            print(
                f"AEMP Fleet fetch failed ({resp.status_code}): {resp.text[:200]}",
                file=sys.stderr,
            )
            break

        xml_text = resp.text
        pages.append(xml_text)

        # Check for next link
        if "<rel>next</rel>" not in xml_text and 'rel="next"' not in xml_text:
            break

        page_number += 1

    return pages


# ---------------------------------------------------------------------------
# ISO 15143-3 XML Parsing
# ---------------------------------------------------------------------------


def _text(el: ET.Element | None) -> str | None:
    """Get text content of an element, or None."""
    return el.text.strip() if el is not None and el.text else None


def _float(el: ET.Element | None) -> float | None:
    """Parse float from element text, or None."""
    text = _text(el)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _find(parent: ET.Element, tag: str) -> ET.Element | None:
    """Find a child element, trying both namespaced and plain tag names."""
    # Try with namespace
    el = parent.find(f"ns:{tag}", NS_MAP)
    if el is not None:
        return el
    # Try without namespace
    return parent.find(tag)


def _findall(parent: ET.Element, tag: str) -> list[ET.Element]:
    """Find all child elements, trying both namespaced and plain tag names."""
    els = parent.findall(f"ns:{tag}", NS_MAP)
    if els:
        return els
    return parent.findall(tag)


def _parse_fleet_xml(xml_pages: list[str]) -> list[dict]:
    """Parse ISO 15143-3 AEMP XML pages into equipment records."""
    equipment: list[dict] = []

    for xml_text in xml_pages:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"XML parse error: {e}", file=sys.stderr)
            continue

        # Handle root element which may be <Fleet> with or without namespace
        eq_elements = _findall(root, "Equipment")

        for eq in eq_elements:
            header = _find(eq, "EquipmentHeader")
            location = _find(eq, "Location")
            hours = _find(eq, "CumulativeOperatingHours")
            idle = _find(eq, "CumulativeIdleHours")
            fuel_used = _find(eq, "FuelUsed")
            fuel_remaining = _find(eq, "FuelRemaining")
            def_remaining = _find(eq, "DEFRemaining")

            # Parse equipment ID
            eq_id_text = _text(_find(header, "EquipmentID")) if header else None
            if eq_id_text and eq_id_text.startswith("PIN:"):
                eq_id_text = eq_id_text[4:]

            serial = _text(_find(header, "SerialNumber")) if header else None

            # Location datetime from attribute or child element
            loc_dt = None
            if location is not None:
                loc_dt = location.get("datetime") or _text(
                    _find(location, "DateTime")
                )

            # Hours datetime from attribute
            hours_dt = hours.get("datetime") if hours is not None else None

            record = {
                "equipmentId": eq_id_text or "",
                "serialNumber": serial or eq_id_text or "",
                "model": _text(_find(header, "Model")) if header else None,
                "oemName": (
                    _text(_find(header, "OEMName")) if header else "John Deere"
                ),
                "latitude": _float(_find(location, "Latitude")) if location else None,
                "longitude": _float(_find(location, "Longitude")) if location else None,
                "locationDateTime": loc_dt,
                "engineHours": _float(_find(hours, "Hour")) if hours else None,
                "engineHoursDateTime": hours_dt,
                "idleHours": _float(_find(idle, "Hour")) if idle else None,
                "fuelConsumedLitres": (
                    _float(_find(fuel_used, "FuelConsumed")) if fuel_used else None
                ),
                "fuelRemainingPercent": (
                    _float(_find(fuel_remaining, "Percent"))
                    if fuel_remaining
                    else None
                ),
                "defRemainingPercent": (
                    _float(_find(def_remaining, "Percent"))
                    if def_remaining
                    else None
                ),
            }
            equipment.append(record)

    return equipment


# ---------------------------------------------------------------------------
# Equipment Matching
# ---------------------------------------------------------------------------


def _build_serial_map(
    supabase_url: str, service_key: str
) -> dict[str, dict[str, str | None]]:
    """Build a mapping of serial/VIN → {code, hcssId} from the Equipment table."""
    sb = create_client(supabase_url, service_key)
    resp = sb.table("Equipment").select("code, hcssId, serialNumber, vin").execute()

    serial_map: dict[str, dict[str, str | None]] = {}
    for row in resp.data or []:
        entry = {"code": row["code"], "hcssId": row.get("hcssId")}
        if row.get("serialNumber"):
            serial_map[str(row["serialNumber"]).upper()] = entry
        if row.get("vin"):
            serial_map[str(row["vin"]).upper()] = entry

    return serial_map


# ---------------------------------------------------------------------------
# Snapshot Mapping
# ---------------------------------------------------------------------------


def _map_snapshot(
    record: dict,
    snapshot_at: datetime,
    serial_map: dict[str, dict[str, str | None]],
) -> dict | None:
    """Map a parsed AEMP equipment record to a TelematicsSnapshot row."""
    serial = str(record.get("serialNumber", "")).upper()
    eq_id = str(record.get("equipmentId", "")).upper()
    match = serial_map.get(serial) or serial_map.get(eq_id)

    if not match:
        return None

    # Staleness check
    is_stale = False
    loc_dt_str = record.get("locationDateTime")
    if loc_dt_str:
        try:
            loc_dt = datetime.fromisoformat(loc_dt_str.replace("Z", "+00:00"))
            delta = (snapshot_at - loc_dt).total_seconds()
            is_stale = delta > STALE_THRESHOLD_SECONDS
        except (ValueError, TypeError):
            is_stale = True

    engine_hours = record.get("engineHours")
    idle_hours = record.get("idleHours")
    productive_hours = (
        engine_hours - idle_hours
        if engine_hours is not None and idle_hours is not None
        else None
    )

    return {
        "equipmentCode": match["code"],
        "equipmentHcssId": match.get("hcssId"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "locationDateTime": loc_dt_str,
        "isLocationStale": is_stale,
        "hourMeterReadingInHours": engine_hours,
        "hourMeterReadingDateTime": record.get("engineHoursDateTime"),
        "hourMeterReadingSource": "jdlink",
        "idleHours": idle_hours,
        "productiveHours": productive_hours,
        "fuelRemainingPercent": record.get("fuelRemainingPercent"),
        "fuelConsumedLitres": record.get("fuelConsumedLitres"),
        "defRemainingPercent": record.get("defRemainingPercent"),
        "providerKey": "jdlink",
        "snapshotAt": snapshot_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI Command
# ---------------------------------------------------------------------------


@app.command("jdlink")
def sync_jdlink(
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and parse only; do not write to Supabase"),
    sandbox: bool = typer.Option(False, "--sandbox", help="Use JDLink sandbox endpoint"),
) -> None:
    """Sync John Deere JDLink telemetry via AEMP ISO 15143-3 API."""
    # Resolve credentials
    app_id = os.environ.get("JDLINK_APP_ID")
    secret = os.environ.get("JDLINK_SECRET")
    refresh_token = os.environ.get("JDLINK_REFRESH_TOKEN")
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
        "SUPABASE_SERVICE_KEY"
    )

    missing = []
    if not app_id:
        missing.append("JDLINK_APP_ID")
    if not secret:
        missing.append("JDLINK_SECRET")
    if not refresh_token:
        missing.append("JDLINK_REFRESH_TOKEN")
    if not supabase_url:
        missing.append("SUPABASE_URL")
    if not service_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        print(f"Missing required config: {', '.join(missing)}", file=sys.stderr)
        raise typer.Exit(code=1)

    start = time.time()
    base_url = AEMP_BASE_SANDBOX if sandbox else AEMP_BASE_PROD

    # 1. Authenticate
    print("Authenticating to John Deere JDLink ...")
    token = _get_jdlink_token(app_id, secret, refresh_token)
    print("  OK\n")

    # 2. Build equipment serial map
    print("Loading equipment serial/VIN map ...")
    serial_map = _build_serial_map(supabase_url, service_key)
    print(f"  {len(serial_map)} serial/VIN entries\n")

    # 3. Fetch AEMP fleet data
    env_label = "sandbox" if sandbox else "production"
    print(f"Fetching AEMP fleet data ({env_label}) ...")
    xml_pages = _fetch_fleet_pages(token, base_url)
    print(f"  {len(xml_pages)} page(s) fetched\n")

    # 4. Parse XML
    print("Parsing ISO 15143-3 XML ...")
    all_equipment = _parse_fleet_xml(xml_pages)
    print(f"  {len(all_equipment)} equipment records\n")

    # 5. Map to snapshots
    snapshot_at = datetime.now(timezone.utc)
    snapshots: list[dict] = []
    unmatched = 0

    for record in all_equipment:
        row = _map_snapshot(record, snapshot_at, serial_map)
        if row:
            snapshots.append(row)
        else:
            unmatched += 1

    stale_count = sum(1 for s in snapshots if s.get("isLocationStale"))
    has_gps = sum(1 for s in snapshots if s.get("latitude") is not None)

    # Summary
    duration = time.time() - start
    print(f"{'=' * 50}")
    prefix = "DRY RUN — " if dry_run else ""
    print(f"{prefix}JDLink Sync Summary:")
    print(f"  AEMP records:      {len(all_equipment):>6}")
    print(f"  Matched snapshots: {len(snapshots):>6}")
    print(f"  Unmatched:         {unmatched:>6}")
    print(f"  With GPS:          {has_gps:>6}")
    print(f"  Stale GPS:         {stale_count:>6}")
    print(f"  Duration:          {duration:>6.1f}s")

    if dry_run:
        print(f"\nDry run complete. No data written to Supabase.")
        return

    # 6. Insert into Supabase
    print(f"\nWriting {len(snapshots)} snapshots to Supabase ...")
    sb = create_client(supabase_url, service_key)
    errors: list[str] = []
    inserted = 0

    for i in range(0, len(snapshots), INSERT_BATCH_SIZE):
        batch = snapshots[i : i + INSERT_BATCH_SIZE]
        try:
            sb.table("TelematicsSnapshot").insert(batch).execute()
            inserted += len(batch)
        except Exception as e:
            msg = f"Batch {i // INSERT_BATCH_SIZE + 1}: {e}"
            errors.append(msg)
            print(f"  FAILED: {msg}", file=sys.stderr)

    total_duration = time.time() - start
    print(f"\n{'=' * 50}")
    print(f"Sync complete.")
    print(f"  Inserted:          {inserted:>6} snapshots")
    print(f"  Duration:          {total_duration:>6.1f}s")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        raise typer.Exit(code=1)
    else:
        print(f"  Errors:            none")
