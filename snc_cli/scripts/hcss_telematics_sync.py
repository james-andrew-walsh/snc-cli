#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  DEPRECATED — Superseded by Supabase Edge Function                 ║
║                                                                    ║
║  This script has been replaced by the telemetrics-sync Edge        ║
║  Function at:                                                      ║
║    core/supabase/functions/telemetrics-sync/                       ║
║                                                                    ║
║  The Edge Function runs on a 3-hour cron schedule and supports     ║
║  multiple OEM telematics providers (HCSS-010).                     ║
║                                                                    ║
║  This file is kept for reference only. Do not use in production.   ║
╚══════════════════════════════════════════════════════════════════════╝

HCSS Telematics Sync — appends GPS/engine-hour snapshots into Supabase.

Fetches the latest telematics reading for every registered machine from the
HCSS Telematics API and inserts a new row into TelematicsSnapshot for each.
This is append-only — every run adds new rows, nothing is updated or deleted.

Usage:
    python -m snc_cli.scripts.hcss_telematics_sync --dry-run
    python -m snc_cli.scripts.hcss_telematics_sync
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta

import httpx
from supabase import create_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HCSS_TOKEN_URL = "https://api.hcssapps.com/identity/connect/token"
TELEMATICS_BASE = "https://api.hcssapps.com/telematics/api/v1"

HCSS_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

INSERT_BATCH_SIZE = 500
STALE_THRESHOLD_HOURS = 4

# ---------------------------------------------------------------------------
# HCSS Authentication
# ---------------------------------------------------------------------------


def get_hcss_token(client_id: str, client_secret: str) -> str:
    """Obtain an OAuth2 access token from HCSS (client_credentials grant)."""
    resp = httpx.post(
        HCSS_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "telematics:read",
        },
        headers={"User-Agent": HCSS_USER_AGENT},
    )
    if resp.status_code != 200:
        print(f"HCSS auth failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(1)
    token = resp.json().get("access_token")
    if not token:
        print("HCSS auth response missing access_token", file=sys.stderr)
        sys.exit(1)
    return token


# ---------------------------------------------------------------------------
# HCSS Data Fetching
# ---------------------------------------------------------------------------


def _hcss_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": HCSS_USER_AGENT,
        "Accept": "application/json",
    }


def _get_with_retry(
    url: str, headers: dict, params: dict | None = None, retries: int = 8
) -> httpx.Response:
    """GET with automatic retry on 429 rate-limit responses."""
    resp = None
    for attempt in range(retries):
        resp = httpx.get(url, headers=headers, params=params or {}, timeout=60)
        if resp.status_code != 429:
            return resp
        wait = 2.0
        try:
            m = re.search(r"(\d+) second", resp.text)
            if m:
                wait = float(m.group(1)) + 0.5
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(wait)
    return resp  # type: ignore[return-value]


def fetch_telematics(headers: dict) -> list[dict]:
    """Fetch all telematics equipment records (paginated).

    The Telematics API uses cursor-based pagination similar to E360:
    { count, next, timestamp, data: [...] }
    """
    print("  Telematics Equipment ... ", end="", flush=True)
    all_records: list[dict] = []
    params: dict = {}
    page = 0

    while True:
        if page > 0:
            time.sleep(1.5)
        page += 1

        resp = _get_with_retry(f"{TELEMATICS_BASE}/equipment", headers, params)
        if resp.status_code != 200:
            print(f"FAILED ({resp.status_code}): {resp.text[:200]}", file=sys.stderr)
            break
        body = resp.json()
        if isinstance(body, list):
            all_records.extend(body)
            break
        # Telematics API wraps in "results"; fall back to "data" and other keys
        page_data = None
        for key in ("results", "data", "items", "value"):
            if key in body and isinstance(body[key], list):
                page_data = body[key]
                break
        if page_data is None:
            page_data = []
        all_records.extend(page_data)
        next_cursor = body.get("next")
        if not next_cursor or not page_data:
            break
        params = {"cursor": next_cursor}

    has_gps = sum(1 for r in all_records if r.get("lastLatitude") is not None)
    print(f"{len(all_records)} total, {has_gps} with GPS")
    return all_records


# ---------------------------------------------------------------------------
# Equipment Lookup
# ---------------------------------------------------------------------------


def build_equipment_code_map(supabase) -> dict[str, str]:
    """Build a mapping of equipment code -> hcssId from the Equipment table."""
    print("  Loading Equipment code map ... ", end="", flush=True)
    result = supabase.table("Equipment").select("code,hcssId").execute()
    code_map = {}
    for row in result.data or []:
        code = row.get("code")
        hcss_id = row.get("hcssId")
        if code and hcss_id:
            code_map[code] = hcss_id
    print(f"{len(code_map)} codes")
    return code_map


# ---------------------------------------------------------------------------
# Snapshot Mapping
# ---------------------------------------------------------------------------


def map_snapshot(r: dict, snapshot_at: datetime, code_map: dict[str, str]) -> dict:
    """Map a telematics API record to a TelematicsSnapshot row."""
    code = r.get("code", "")

    # Parse locationDateTime to check staleness
    location_dt_str = r.get("lastLocationDateTime")
    location_dt = None
    is_stale = False
    if location_dt_str:
        try:
            location_dt = datetime.fromisoformat(location_dt_str.replace("Z", "+00:00"))
            is_stale = (snapshot_at - location_dt) > timedelta(hours=STALE_THRESHOLD_HOURS)
        except (ValueError, TypeError):
            is_stale = True  # Can't parse = treat as stale

    # Parse other datetime fields
    hour_meter_dt_str = r.get("lastHourMeterReadingDateTime")
    engine_status_dt_str = r.get("lastEngineStatusDateTime")

    return {
        "equipmentCode": code,
        "equipmentHcssId": code_map.get(code),
        "latitude": r.get("lastLatitude"),
        "longitude": r.get("lastLongitude"),
        "locationDateTime": location_dt_str,
        "isLocationStale": is_stale,
        "hourMeterReadingInHours": r.get("lastHourMeterReadingInHours"),
        "hourMeterReadingDateTime": hour_meter_dt_str,
        "hourMeterReadingSource": r.get("lastHourMeterReadingSource"),
        "engineStatus": r.get("lastEngineStatus"),
        "engineStatusDateTime": engine_status_dt_str,
        "snapshotAt": snapshot_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync HCSS Telematics snapshots into Supabase"
    )
    parser.add_argument(
        "--hcss-client-id",
        default=None,
        help="HCSS OAuth2 client ID (or HCSS_CLIENT_ID env)",
    )
    parser.add_argument(
        "--hcss-client-secret",
        default=None,
        help="HCSS OAuth2 client secret (or HCSS_CLIENT_SECRET env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and count only; do not write to Supabase",
    )
    args = parser.parse_args()

    # Resolve credentials
    hcss_id = args.hcss_client_id or os.environ.get("HCSS_CLIENT_ID")
    hcss_secret = args.hcss_client_secret or os.environ.get("HCSS_CLIENT_SECRET")
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
        "SUPABASE_SERVICE_KEY"
    )

    missing = []
    if not hcss_id:
        missing.append("HCSS_CLIENT_ID")
    if not hcss_secret:
        missing.append("HCSS_CLIENT_SECRET")
    if not supabase_url:
        missing.append("SUPABASE_URL")
    if not service_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        print(f"Missing required config: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    start = time.time()
    snapshot_at = datetime.now(timezone.utc)

    # 1. Authenticate to HCSS
    print("Authenticating to HCSS ...")
    token = get_hcss_token(hcss_id, hcss_secret)
    headers = _hcss_headers(token)
    print("  OK\n")

    # 2. Connect to Supabase and build equipment code map
    print("Loading reference data:")
    sb = create_client(supabase_url, service_key)
    code_map = build_equipment_code_map(sb)
    print()

    # 3. Fetch telematics data
    print("Fetching data from HCSS Telematics API:")
    records = fetch_telematics(headers)

    if not records:
        print("\nNo telematics records returned. Exiting.")
        return

    # 4. Map to snapshot rows
    snapshots = [map_snapshot(r, snapshot_at, code_map) for r in records]
    stale_count = sum(1 for s in snapshots if s["isLocationStale"])
    has_gps = sum(1 for s in snapshots if s.get("latitude") is not None)
    matched = sum(1 for s in snapshots if s.get("equipmentHcssId") is not None)

    # 5. Summary
    duration = time.time() - start
    print(f"\n{'=' * 50}")
    prefix = "DRY RUN — " if args.dry_run else ""
    print(f"{prefix}Telematics Sync Summary:")
    print(f"  Total records:     {len(snapshots):>6,}")
    print(f"  With GPS:          {has_gps:>6,}")
    print(f"  Stale GPS:         {stale_count:>6,}")
    print(f"  Matched to E360:   {matched:>6,}")
    print(f"  Fetch duration:    {duration:>6.1f}s")

    if args.dry_run:
        print(f"\nDry run complete. No data written to Supabase.")
        return

    # 6. Insert snapshots (append-only)
    print(f"\nInserting {len(snapshots):,} snapshots into TelematicsSnapshot ...")
    errors: list[str] = []
    inserted = 0
    for i in range(0, len(snapshots), INSERT_BATCH_SIZE):
        batch = snapshots[i : i + INSERT_BATCH_SIZE]
        try:
            sb.table("TelematicsSnapshot").insert(
                batch, returning="minimal", count=None
            ).execute()
            inserted += len(batch)
            print(f"  Batch {i // INSERT_BATCH_SIZE + 1}: {len(batch)} rows OK")
        except Exception as e:
            msg = f"Batch {i // INSERT_BATCH_SIZE + 1}: {e}"
            errors.append(msg)
            print(f"  {msg}", file=sys.stderr)

    total_duration = time.time() - start
    print(f"\n{'=' * 50}")
    print(f"Sync complete.")
    print(f"  Snapshots inserted: {inserted:>6,}")
    print(f"  Stale GPS:          {stale_count:>6,}")
    print(f"  Duration:           {total_duration:>6.1f}s")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"  Errors:             none")


if __name__ == "__main__":
    main()
