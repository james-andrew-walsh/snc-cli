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

## Current Task: HCSS-001
**CR:** `core/CHANGE-REQUEST-HCSS-001-HCSS-SYNC-LAYER.md`

### Step 1: Apply Migration 011
File to create: `core/supabase/migrations/011_add_job_equipment.sql`
SQL is in the CR. Apply via Supabase Management API.

### Step 2: Create Sync Script
File to create: `snc_cli/scripts/hcss_sync.py`
- Fetch all 5 tables from HCSS
- Clear-and-replace each mirror table in a transaction
- Print summary counts
- Support `--dry-run` flag

### Verify
```bash
python snc_cli/scripts/hcss_sync.py --dry-run   # should show expected counts
python snc_cli/scripts/hcss_sync.py              # populate Supabase
```

After sync:
- Check Equipment count (~900)
- Check Job count (~235)
- Check JobEquipment count (large — all active-job authorizations)

## Definition of Done
- [ ] Migration 011 applied to Supabase (JobEquipment table exists)
- [ ] `snc_cli/scripts/hcss_sync.py` exists and runs without errors
- [ ] `--dry-run` prints expected record counts without writing
- [ ] Full sync populates all 5 mirror tables
- [ ] Re-running sync produces same results (idempotent)
- [ ] All changes committed and pushed to GitHub

## Do NOT
- Touch value-add tables (SiteLocation, TelematicsSnapshot, ReconciliationRun, Anomaly)
- Use upsert for mirror tables — use clear-and-replace (truncate + insert in transaction)
- Use the `/jobs/{id}/equipment` HeavyJob path — it returns 404
- Omit the browser User-Agent header on HCSS requests
- Store credentials in code — use env vars only
