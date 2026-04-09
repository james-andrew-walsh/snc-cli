# CLAUDE.md — SNC Equipment Tracking

## Project Overview
SNC Equipment Tracking: syncs HCSS APIs (E360, HeavyJob, Telematics) into Supabase, adds a geographic layer, and runs reconciliation to detect equipment anomalies.

## Repo Layout
```
projects/SNC/equipment-tracking/
├── CLAUDE.md                    # This file
├── EQUIPMENT-TRACKING-PROJECT.md # Full PRD — current system state
├── PROBLEM-AND-VISION.md        # Why this exists and what we're building
├── DATA_MAPPING.md              # HCSS API field mapping reference
├── core/
│   ├── CHANGE-REQUEST-*.md      # Specs for each feature (implement from these)
│   ├── supabase/migrations/     # SQL migrations (001–010 applied)
│   └── CORE-ARCHITECTURE.md    # Architecture reference
└── snc_cli/
    └── scripts/                 # Python scripts (new scripts go here)
```

CLI repo: github.com/james-andrew-walsh/snc-cli (clone locally if needed)
Dashboard repo: github.com/james-andrew-walsh/snc-dashboard

## Build & Run Commands
```bash
# Python environment
pip install -r requirements.txt  # if it exists in snc-cli repo

# Run sync script (once created)
python snc_cli/scripts/hcss_sync.py --dry-run
python snc_cli/scripts/hcss_sync.py

# Apply a Supabase migration (via Management API)
# See "Applying Migrations" section below
```

## Environment Variables Required
```
HCSS_CLIENT_ID          # HCSS OAuth2 client ID
HCSS_CLIENT_SECRET      # HCSS OAuth2 client secret
SUPABASE_URL            # https://ghscnwwatguzmeuabspd.supabase.co
SUPABASE_SERVICE_ROLE_KEY  # Service role key (bypasses RLS — sync only)
SUPABASE_KEY            # Anon key (for CLI user-auth flows)
```

## Supabase Project
- **Project ref:** `ghscnwwatguzmeuabspd`
- **URL:** `https://ghscnwwatguzmeuabspd.supabase.co`
- **Migrations applied:** 001–010 (schema fully expanded for HCSS fields)
- **Service role key:** use `SUPABASE_SERVICE_ROLE_KEY` env var (bypasses RLS for sync)

### Applying Migrations via Management API
```python
import os, requests

supabase_ref = "ghscnwwatguzmeuabspd"
# Get token from: https://app.supabase.com/account/tokens
mgmt_token = os.environ["SUPABASE_MANAGEMENT_TOKEN"]

sql = open("core/supabase/migrations/011_add_job_equipment.sql").read()
resp = requests.post(
    f"https://api.supabase.com/v1/projects/{supabase_ref}/database/query",
    headers={
        "Authorization": f"Bearer {mgmt_token}",
        "Content-Type": "application/json",
        "User-Agent": "curl/8.1.2",  # CRITICAL — Cloudflare blocks without this
    },
    json={"query": sql}
)
```

## HCSS API
- **Auth:** POST `https://api.hcssapps.com/identity/connect/token` (client_credentials)
- **Scope:** `e360:read heavyjob:read`
- **CRITICAL:** All requests must include:
  ```
  User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
  ```
- **E360 base:** `https://api.hcssapps.com/e360/api/v1/`
- **HeavyJob base:** `https://api.hcssapps.com/heavyjob/api/v1/`

### Key Endpoints
- Equipment: `GET /e360/api/v1/equipment?pageSize=1000`
- Jobs: `GET /heavyjob/api/v1/jobs?pageSize=500&status=active`
- Locations: `GET /e360/api/v1/locations?pageSize=1000`
- Business Units (E360): `GET /e360/api/v1/businessUnits`
- Business Units (HJ): `GET /heavyjob/api/v1/businessUnits`
- **JobEquipment:** `GET /heavyjob/api/v1/jobEquipment?businessUnitId={BU}&jobId={JOB_ID}&pageSize=1000`
  - ⚠️ Pagination cycles after page 2 — only pull page 1 (1,000 records max per job)
  - ⚠️ `/jobs/{id}/equipment` returns 404 — do NOT use that path

## Database Schema (Mirror Tables — HCSS-001 target)
All tables use camelCase column names matching HCSS field names exactly.

Mirror tables (truncated + replaced on every sync):
- `BusinessUnit` — from E360 + HeavyJob
- `Equipment` — from E360 (status: AVAIL, IN SERVICE, STANDBY)
- `Job` — from HeavyJob (status: active)
- `Location` — from E360 (all)
- `JobEquipment` — from HeavyJob jobEquipment endpoint (NEW — migration 011)

Value-add tables (NEVER touched by sync):
- `SiteLocation`, `SiteLocationJob` — geofences (future)
- `TelematicsSnapshot` — GPS time-series (future)
- `ReconciliationRun`, `Anomaly` — reconciliation output (future)

## Completed: HCSS-001 ✅
- Migration 011 applied (JobEquipment table)
- `snc_cli/scripts/hcss_sync.py` implemented and verified
- Counts: 2 BU, 753 Equipment, 236 Jobs, 3,090 Locations, 22,678 JobEquipment
- Commit: 569aebf

## Current Task: HCSS-003
**CR:** `/Users/james/.openclaw/workspace/projects/SNC/equipment-tracking/core/CHANGE-REQUEST-HCSS-003-TELEMATICS-SNAPSHOTS.md`

Read the full CR before starting.

### Step 1: Apply Migration 012
File to create: `core/supabase/migrations/012_add_telematics_snapshot.sql`

SQL:
```sql
CREATE TABLE IF NOT EXISTS "TelematicsSnapshot" (
    "id"                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "equipmentCode"               text NOT NULL,
    "equipmentHcssId"             uuid,
    "latitude"                    double precision,
    "longitude"                   double precision,
    "locationDateTime"            timestamptz,
    "isLocationStale"             boolean NOT NULL DEFAULT false,
    "hourMeterReadingInHours"     double precision,
    "hourMeterReadingDateTime"    timestamptz,
    "hourMeterReadingSource"      text,
    "engineStatus"                text,
    "engineStatusDateTime"        timestamptz,
    "snapshotAt"                  timestamptz NOT NULL DEFAULT now(),
    "createdAt"                   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON "TelematicsSnapshot"("equipmentCode");
CREATE INDEX ON "TelematicsSnapshot"("snapshotAt");
CREATE INDEX ON "TelematicsSnapshot"("isLocationStale");
```

Apply via Supabase Management API (SUPABASE_ACCESS_TOKEN env var; User-Agent: curl/8.1.2).

### Step 2: Create `snc_cli/scripts/hcss_telematics_sync.py`

- Auth: HCSS OAuth2 with scope `telematics:read`
- Fetch: `GET https://api.hcssapps.com/telematics/api/v1/equipment` (all pages)
- For each record: insert a new row into TelematicsSnapshot (NEVER upsert — append only)
- Set `isLocationStale = true` if `locationDateTime` is more than 4 hours before `snapshotAt`
- Look up `equipmentHcssId` from the Equipment table by `equipmentCode` (code field)
- Use SUPABASE_SERVICE_ROLE_KEY for writes
- Support `--dry-run` flag
- Print summary: N snapshots recorded, N stale GPS, duration, errors
- Same User-Agent header requirement as hcss_sync.py

See `snc_cli/scripts/hcss_sync.py` for the exact patterns to follow (auth, retry, pagination).

### Verify
```bash
python3 snc_cli/scripts/hcss_telematics_sync.py --dry-run  # show counts
python3 snc_cli/scripts/hcss_telematics_sync.py            # insert first snapshot batch
python3 snc_cli/scripts/hcss_telematics_sync.py            # run again — row count should increase
```

## Definition of Done
- [ ] Migration 012 applied (TelematicsSnapshot table exists)
- [ ] `snc_cli/scripts/hcss_telematics_sync.py` created and runs without errors
- [ ] `--dry-run` shows expected snapshot count (~585 records with GPS)
- [ ] Full run inserts rows into TelematicsSnapshot
- [ ] Second run APPENDS new rows (count increases, not stays same)
- [ ] `isLocationStale` correctly set for machines with stale GPS
- [ ] All changes committed and pushed to GitHub

## Do NOT
- Upsert or update TelematicsSnapshot — it is append-only, every run adds new rows
- Delete any rows from TelematicsSnapshot
- Touch Equipment, Job, Location, BusinessUnit, or JobEquipment tables
- Store credentials in code — env vars only
