#!/usr/bin/env python3
"""HCSS Sync Layer — pulls mirror data from HCSS APIs into Supabase.

Fetches BusinessUnit, Equipment, Job, Location, and JobEquipment from
HCSS E360 and HeavyJob APIs, then clear-and-replaces the corresponding
Supabase mirror tables.

Usage:
    python -m snc_cli.scripts.hcss_sync --dry-run
    python -m snc_cli.scripts.hcss_sync
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone

import httpx
from supabase import create_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HCSS_TOKEN_URL = "https://api.hcssapps.com/identity/connect/token"
E360_BASE = "https://api.hcssapps.com/e360/api/v1"
HEAVYJOB_BASE = "https://api.hcssapps.com/heavyjob/api/v1"

HCSS_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

INSERT_BATCH_SIZE = 500

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
            "scope": "e360:read heavyjob:read",
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


def _fetch_list(url: str, headers: dict, params: dict | None = None) -> list[dict]:
    """Fetch a single-page list endpoint, handling array and wrapped responses."""
    resp = _get_with_retry(url, headers, params)
    if resp.status_code != 200:
        print(f"GET {url} failed ({resp.status_code}): {resp.text[:200]}", file=sys.stderr)
        return []
    data = resp.json()
    if isinstance(data, list):
        return data
    # Wrapped response — try common keys
    for key in ("results", "data", "items", "value"):
        if key in data and isinstance(data[key], list):
            return data[key]
    return []


def _fetch_e360_paginated(url: str, headers: dict) -> list[dict]:
    """Fetch all pages from an E360 cursor-paginated endpoint.

    E360 returns: { count, next, timestamp, data: [...] }
    The `next` field is a cursor passed as ?next= for the next page.
    When `next` is null, we've reached the last page.
    """
    all_records: list[dict] = []
    params: dict = {}
    page = 0

    while True:
        # Rate-limit guard: pause between pages
        if page > 0:
            time.sleep(1.5)
        page += 1

        resp = _get_with_retry(url, headers, params)
        if resp.status_code != 200:
            print(f"GET {url} failed ({resp.status_code}): {resp.text[:200]}", file=sys.stderr)
            break
        body = resp.json()
        if isinstance(body, list):
            all_records.extend(body)
            break
        page_data = body.get("data", [])
        all_records.extend(page_data)
        next_cursor = body.get("next")
        if not next_cursor or not page_data:
            break
        params = {"cursor": next_cursor}

    return all_records


def fetch_e360_business_units(headers: dict) -> list[dict]:
    print("  E360 BusinessUnits ... ", end="", flush=True)
    rows = _fetch_list(f"{E360_BASE}/businessUnits", headers)
    print(f"{len(rows)}")
    return rows


def fetch_heavyjob_business_units(headers: dict) -> list[dict]:
    print("  HeavyJob BusinessUnits ... ", end="", flush=True)
    rows = _fetch_list(f"{HEAVYJOB_BASE}/businessUnits", headers)
    print(f"{len(rows)}")
    return rows


ACTIVE_EQUIPMENT_STATUSES = {"AVAIL", "IN SERVICE", "STANDBY"}


def fetch_equipment(headers: dict) -> list[dict]:
    """Fetch active equipment from E360 (cursor-paginated, ~900 records).

    Filters client-side to status in AVAIL, IN SERVICE, STANDBY.
    """
    print("  E360 Equipment ... ", end="", flush=True)
    all_eq = _fetch_e360_paginated(f"{E360_BASE}/equipment", headers)
    active = [e for e in all_eq if e.get("status") in ACTIVE_EQUIPMENT_STATUSES]
    print(f"{len(active)} active (of {len(all_eq)} total)")
    return active


def fetch_jobs(headers: dict) -> list[dict]:
    """Fetch active jobs from HeavyJob (client-side filter; API returns all)."""
    print("  HeavyJob Jobs ... ", end="", flush=True)
    all_jobs = _fetch_list(f"{HEAVYJOB_BASE}/jobs", headers)
    active = [j for j in all_jobs if j.get("status") == "active"]
    print(f"{len(active)} active (of {len(all_jobs)} total)")
    return active


def fetch_locations(headers: dict) -> list[dict]:
    """Fetch all locations from E360 (cursor-paginated)."""
    print("  E360 Locations ... ", end="", flush=True)
    rows = _fetch_e360_paginated(f"{E360_BASE}/locations", headers)
    print(f"{len(rows)}")
    return rows


def fetch_job_equipment(
    headers: dict, jobs: list[dict], equipment: list[dict]
) -> list[dict]:
    """Fetch jobEquipment for jobs that have active E360 equipment assigned.

    Strategy: collect the unique jobCodes from E360 equipment records,
    then only call the jobEquipment endpoint for those jobs. This filters
    4,893 HeavyJob jobs down to ~200-300 that actually have equipment on them.

    Rate limiting: 1 second delay between calls to avoid 429s.
    Only page 1 per job (HCSS pagination cycles after page 2 — max 1,000 records).
    Only records with isActive=true are kept.
    """
    # Find job codes that have active E360 equipment assigned right now
    active_job_codes = {
        r.get("jobCode") for r in equipment
        if r.get("jobCode") and r.get("status") in ("AVAIL", "IN SERVICE", "STANDBY")
    }
    active_job_codes.discard(None)
    active_job_codes.discard("")

    # Build a lookup of jobCode -> job record from HeavyJob jobs list
    job_by_code = {j.get("code"): j for j in jobs if j.get("code")}

    # Intersect: only jobs that appear in both HeavyJob and E360 active equipment
    target_jobs = [
        job_by_code[code]
        for code in active_job_codes
        if code in job_by_code
    ]

    print(f"  HeavyJob JobEquipment ({len(target_jobs)} jobs with active E360 equipment) ... ", end="", flush=True)

    if not target_jobs:
        print("0")
        return []

    all_records: list[dict] = []
    errors = 0

    for i, job in enumerate(target_jobs):
        job_id = job.get("id")
        bu_id = job.get("businessUnitId")
        if not job_id or not bu_id:
            errors += 1
            continue

        rows = _fetch_list(
            f"{HEAVYJOB_BASE}/jobEquipment",
            headers,
            {"businessUnitId": bu_id, "jobId": job_id, "pageSize": 1000},
        )
        for r in rows:
            if r.get("isActive", True):
                r.setdefault("jobId", job_id)
                r.setdefault("jobCode", job.get("code", ""))
                all_records.append(r)

        if (i + 1) % 50 == 0:
            print(f"{i + 1}...", end="", flush=True)

    suffix = f" ({errors} errors)" if errors else ""
    print(f" {len(all_records)} active records from {len(target_jobs)} jobs{suffix}")
    return all_records


# ---------------------------------------------------------------------------
# Field Mapping  (HCSS → Supabase columns)
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_business_unit(r: dict, source: str) -> dict:
    hcss_id = r.get("id")
    return {
        "id": hcss_id,
        "hcssId": hcss_id,
        "code": r.get("code"),
        "description": r.get("description"),
        "hcssSource": source,
        "credentialsId": r.get("credentialsId"),
        "lastSyncedAt": _now_iso(),
    }


def map_equipment(r: dict) -> dict:
    return {
        "hcssId": r.get("id"),
        "businessUnitId": r.get("businessUnitId"),
        "code": r.get("code"),
        "description": r.get("description"),
        "equipmentType": r.get("equipmentType"),
        "accountingCode": r.get("accountingCode"),
        "make": r.get("make"),
        "model": r.get("model"),
        "year": r.get("year"),
        "vin": r.get("vin"),
        "serialNumber": r.get("serialNo"),
        "status": r.get("status"),
        "enabled": r.get("enabled"),
        "hourMeter": r.get("hourMeter"),
        "odometer": r.get("odometer"),
        "weight": r.get("weight"),
        "length": r.get("length"),
        "width": r.get("width"),
        "height": r.get("height"),
        "numberAxles": r.get("numberAxles"),
        "tireSize": r.get("tireSize"),
        "ratedPowerHP": r.get("ratedPowerHP"),
        "ratedPowerKW": r.get("ratedPowerKW"),
        "defaultFuel": r.get("defaultFuel"),
        "purchaseDate": r.get("purchaseDate"),
        "purchasePrice": r.get("purchasePrice"),
        "jobCode": r.get("jobCode"),
        "locationName": r.get("locationName"),
        "onLoanBusinessUnitId": r.get("onLoanBusinessUnitID"),
        "imageUrl": r.get("imageUrl"),
        "region": r.get("region"),
        "division": r.get("division"),
        "lastSyncedAt": _now_iso(),
    }


def map_job(r: dict) -> dict:
    return {
        "hcssId": r.get("id"),
        "businessUnitId": r.get("businessUnitId"),
        "code": r.get("code"),
        "description": r.get("description"),
        "status": r.get("status"),
        "legacyId": r.get("legacyId"),
        "payItemSetupType": r.get("payItemSetupType"),
        "startofpayweek": r.get("startofpayweek"),
        "relatedEstimateCodes": r.get("relatedEstimateCodes") or [],
        "jobNote": r.get("jobNote"),
        "isDeleted": r.get("isDeleted", False),
        "address": r.get("address"),
        "lastSyncedAt": _now_iso(),
    }


def map_location(r: dict) -> dict:
    return {
        "hcssId": r.get("id"),
        "businessUnitId": r.get("businessUnitId"),
        "code": r.get("code"),
        "description": r.get("description"),
        "altCode": r.get("altCode"),
        "enabled": r.get("enabled"),
        "address": r.get("address"),
        "regionCode": r.get("regionCode"),
        "divisionCode": r.get("divisionCode"),
        "lastSyncedAt": _now_iso(),
    }


def map_job_equipment(r: dict) -> dict:
    return {
        "hcssId": r.get("id"),
        "businessUnitId": r.get("businessUnitId"),
        "businessUnitCode": r.get("businessUnitCode"),
        "jobHcssId": r.get("jobId"),
        "jobCode": r.get("jobCode"),
        "equipmentHcssId": r.get("equipmentId"),
        "equipmentCode": r.get("equipmentCode"),
        "equipmentDescription": r.get("equipmentDescription"),
        "isActive": r.get("isActive", True),
        "operatorPayClassId": r.get("operatorPayClassId"),
        "operatorPayClassCode": r.get("operatorPayClassCode"),
        "lastSyncedAt": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Supabase Write
# ---------------------------------------------------------------------------


def clear_and_replace(supabase, table: str, rows: list[dict]) -> None:
    """Delete all rows from *table*, then bulk-insert *rows* in batches."""
    # Delete all existing rows
    supabase.table(table).delete().gte(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()

    if not rows:
        return

    # Insert in batches
    for i in range(0, len(rows), INSERT_BATCH_SIZE):
        batch = rows[i : i + INSERT_BATCH_SIZE]
        supabase.table(table).insert(batch).execute()


def truncate_all_mirrors(supabase) -> None:
    """Call the sync_truncate_mirrors() RPC to TRUNCATE all mirror tables."""
    supabase.rpc("sync_truncate_mirrors").execute()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync HCSS data into Supabase")
    parser.add_argument(
        "--hcss-client-id", default=None, help="HCSS OAuth2 client ID (or HCSS_CLIENT_ID env)"
    )
    parser.add_argument(
        "--hcss-client-secret", default=None, help="HCSS OAuth2 client secret (or HCSS_CLIENT_SECRET env)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Fetch and count only; do not write to Supabase"
    )
    args = parser.parse_args()

    # Resolve credentials
    hcss_id = args.hcss_client_id or os.environ.get("HCSS_CLIENT_ID")
    hcss_secret = args.hcss_client_secret or os.environ.get("HCSS_CLIENT_SECRET")
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")

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

    # 1. Authenticate to HCSS
    print("Authenticating to HCSS ...")
    token = get_hcss_token(hcss_id, hcss_secret)
    headers = _hcss_headers(token)
    print("  OK\n")

    # 2. Fetch all data from HCSS (before touching Supabase)
    #    Small delays between endpoints to stay under rate limits.
    print("Fetching data from HCSS APIs:")
    bu_e360 = fetch_e360_business_units(headers)
    bu_hj = fetch_heavyjob_business_units(headers)
    time.sleep(1)
    equipment = fetch_equipment(headers)
    time.sleep(1)
    jobs = fetch_jobs(headers)
    time.sleep(1)
    locations = fetch_locations(headers)
    time.sleep(1)
    job_equipment = fetch_job_equipment(headers, jobs, equipment)

    # 3. Map to Supabase format
    tables = {
        "BusinessUnit": [map_business_unit(r, "e360") for r in bu_e360]
        + [map_business_unit(r, "heavyjob") for r in bu_hj],
        "Equipment": [map_equipment(r) for r in equipment],
        "Job": [map_job(r) for r in jobs],
        # Deduplicate locations by (businessUnitId, code) — HCSS may have duplicate codes
        "Location": list({
            (r.get("businessUnitId"), r.get("code")): map_location(r)
            for r in locations
        }.values()),
        "JobEquipment": [map_job_equipment(r) for r in job_equipment],
    }

    # 4. Summary
    duration = time.time() - start
    print(f"\n{'=' * 50}")
    prefix = "DRY RUN — " if args.dry_run else ""
    print(f"{prefix}Sync Summary:")
    for table, rows in tables.items():
        print(f"  {table:20s} {len(rows):>6,} records")
    print(f"  {'':20s} {'':>6s}")
    print(f"  Fetch duration:    {duration:>6.1f}s")

    if args.dry_run:
        print(f"\nDry run complete. No data written to Supabase.")
        return

    # 5. Clear-and-replace all mirror tables
    print(f"\nWriting to Supabase ...")
    sb = create_client(supabase_url, service_key)

    # Truncate all tables atomically via RPC
    print("  Truncating mirror tables ... ", end="", flush=True)
    try:
        truncate_all_mirrors(sb)
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")
        print("Falling back to per-table delete ...", file=sys.stderr)
        # Fallback: delete per table in child-first order
        for table in ["JobEquipment", "Equipment", "Job", "Location", "BusinessUnit"]:
            sb.table(table).delete().gte(
                "id", "00000000-0000-0000-0000-000000000000"
            ).execute()
        print("  Deleted all rows via fallback")

    # Insert in parent-first order
    insert_order = ["BusinessUnit", "Location", "Job", "Equipment", "JobEquipment"]
    errors: list[str] = []
    for table in insert_order:
        rows = tables[table]
        print(f"  Inserting {table} ({len(rows):,} rows) ... ", end="", flush=True)
        if not rows:
            print("skip (0 rows)")
            continue
        try:
            for i in range(0, len(rows), INSERT_BATCH_SIZE):
                batch = rows[i : i + INSERT_BATCH_SIZE]
                # Use upsert for BusinessUnit to preserve HCSS UUID as PK
                if table == "BusinessUnit":
                    sb.table(table).upsert(batch, on_conflict="id").execute()
                else:
                    sb.table(table).insert(batch).execute()
            print("OK")
        except Exception as e:
            msg = f"{table}: {e}"
            errors.append(msg)
            print(f"FAILED: {e}")

    total_duration = time.time() - start
    print(f"\n{'=' * 50}")
    print(f"Sync complete.")
    for table in insert_order:
        print(f"  {table:20s} {len(tables[table]):>6,} records")
    print(f"  Duration:          {total_duration:>6.1f}s")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"  Errors:            none")


if __name__ == "__main__":
    main()
