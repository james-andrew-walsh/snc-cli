# Change Request: HCSS-001 - HCSS Sync Layer

**Project:** SNC Equipment Tracking
**Date:** 2026-04-08
**Updated:** 2026-04-09
**Status:** IMPLEMENTED ✅
**Implemented by:** Claude Code + Bianca
**Commit:** 569aebf (snc-cli), 4ab83de3 (equipment-tracking)

---

## Summary

Implement a sync layer that pulls active data from HCSS APIs and populates our Supabase tables. This replaces the concept of "production environment setup" - instead, we sync HCSS data into our existing environment.

**Key decisions from 2026-04-08 discussion:**
- No separate production environment - use current environment, sync from HCSS
- Daily sync only (6 AM and 6 PM) - no intraday caching complexity needed
- Sync only active jobs (235 from HeavyJob) and active equipment (~900 from E360)
- HCSS is source of truth; our tables are read-only mirrors

**Added 2026-04-09:** The sync must also pull `jobEquipment` records for all active jobs from HeavyJob and cache them in a `JobEquipmentCache` table. This is required for the map status indicators (HCSS-007) and reconciliation engine (HCSS-006) to determine which machines are authorized to charge to which jobs without making live API calls per machine.

**Important:** `jobEquipment` with `isActive=true` means authorized to charge to this job — it does NOT mean the machine is physically deployed there. The equipment cache is the billing authorization list, not the deployment roster. See PROBLEM-AND-VISION.md for the full explanation.

**API note:** The correct endpoint is `GET /heavyjob/api/v1/jobEquipment?businessUnitId={BU}&jobId={JOB_ID}&pageSize=1000`. Pagination cycles after page 2 — effectively 2,000 unique records maximum per job. Sub-paths like `/jobs/{id}/equipment` return 404 and should not be used.

---

## Data Sources & Working Set

| Source | API | Working Set | Notes |
|--------|-----|-------------|-------|
| **Jobs** | HeavyJob | **236 actual** | `status = "active"` client-side filter — API returns all 4,893; active = 236 |
| **Equipment** | E360 | **753 actual** | `status` in (AVAIL, IN SERVICE, STANDBY) — 753 of 1,073 total |
| **Locations** | E360 | **3,090 actual** | All locations; 1 duplicate deduplicated by (businessUnitId, code) |
| **Business Units** | Both | **2 actual** | E360 "Default Business Unit" + HeavyJob "Sierra Nevada Construction" |
| **Job Equipment** | HeavyJob | **22,678 actual** | Called only for the 27 jobs that have active E360 equipment assigned — not all 236 active jobs |

**Key discovery during implementation:** `status=active` query param is ignored by the HeavyJob jobs API — it returns all 4,893 jobs regardless. Active jobs are filtered client-side by checking `status == "active"` on each record. Result: 236 jobs.

**JobEquipment working set discovery:** We do not call `jobEquipment` for all 236 active jobs. Instead, we collect the unique `jobCode` values from active E360 equipment records and only call `jobEquipment` for those jobs. This produces 27 jobs × ~800 authorizations = 22,678 records — far fewer than 236 × 800 = 188,800 would have been.

**Why this working set:**
- HeavyJob's 236 active jobs are where time cards are being entered *now*
- E360's ~900 active equipment are the pieces that move and get tracked
- Telematics has 468 registered devices - subset of the equipment we'll sync

---

## Schema Changes

### Migration 010: Expand Schema to Match HCSS

**File:** `core/supabase/migrations/010_add_hcss_fields.sql`

This migration expands our tables to match HCSS API fields exactly. See the migration file for full details.

**Summary of changes:**

**All tables:**
- Add `hcssId` (UUID) with unique index for upsert matching
- Add `lastSyncedAt` (timestamp) to track freshness

**Equipment table:**
- Add all E360 fields: equipmentType, accountingCode, vin, weight, length, width, height, numberAxles, tireSize, status, enabled, ratedPowerHP, ratedPowerKW, defaultFuel, purchaseDate, purchasePrice, jobCode, locationName, onLoanBusinessUnitId, imageUrl, region, division

**Job table:**
- Add HeavyJob fields: legacyId, payItemSetupType, startofpayweek, relatedEstimateCodes, jobNote, isDeleted
- Add address as jsonb (stores HCSS address object with line1, line2, city, state, zip)
- Add geographic fields: latitude, longitude, regionCode, divisionCode

**Location table:**
- Add E360 fields: altCode, enabled, address (jsonb), regionCode, divisionCode
- Add geographic fields: latitude, longitude

**BusinessUnit table:**
- Add `hcssSource` to track if BU came from E360 or HeavyJob
- Add `credentialsId` from HeavyJob

**Applied by:** Claude Code as Step 1 of this change request implementation

---

## Sync Architecture

### Approach: Manual Sync (Scheduling in HCSS-002)

**Frequency:** Manual execution via CLI for now
**Direction:** One-way (HCSS → Supabase)
**Scope:** Active jobs and equipment only
**Sync strategy:** Clear-and-replace for all mirror tables (see below)

### Sync Strategy: Clear-and-Replace (Not Upsert)

All mirror tables use **delete-all + bulk insert**, not upsert. Upsert cannot remove records that no longer exist in HCSS — a deactivated machine, completed job, or removed equipment assignment would stay in our tables indefinitely if we only upsert.

**Implementation note:** The supabase-py RPC call to `sync_truncate_mirrors()` was found to silently no-op during testing (printed OK but left data intact). The working implementation uses direct httpx DELETE requests with the service role key against the PostgREST REST API, one table at a time in child-first FK order.

**Tables that are cleared on every sync (HCSS mirrors):**
- `Equipment` — truncated, then bulk inserted from E360
- `Job` — truncated, then bulk inserted from HeavyJob
- `Location` — truncated, then bulk inserted from E360
- `BusinessUnit` — truncated, then bulk inserted from both APIs
- `JobEquipment` — truncated, then bulk inserted from HeavyJob `jobEquipment` endpoint

**Tables that are NEVER touched by sync (value-add):**
- `SiteLocation`, `SiteLocationJob` — our geofence data, never wiped
- `TelematicsSnapshot` — append-only, each sync adds new rows, never deletes
- `ReconciliationRun`, `Anomaly` — our analysis output, never wiped

**Implementation note:** Use Supabase service role key for sync (bypasses RLS). Wrap each table's truncate + insert in a transaction so partial failures do not leave tables empty.

**Note:** Automated scheduling (cron) will be added in HCSS-002. For now, operators run sync manually when needed.

### Sync Script: `snc_cli/scripts/hcss_sync.py`

**Arguments:**
```bash
python snc_cli/scripts/hcss_sync.py \
  --hcss-client-id [CLIENT_ID] \
  --hcss-client-secret [CLIENT_SECRET] \
  [--dry-run]
```

**Environment variables:**
- `HCSS_CLIENT_ID` / `HCSS_CLIENT_SECRET` - OAuth2 credentials
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` - Supabase connection

**Logic:**
```
1. Get HCSS OAuth2 tokens (scope: e360:read heavyjob:read)

2. Fetch all data from HCSS APIs (before touching Supabase):
   a. Business Units — E360 + HeavyJob
   b. Jobs — HeavyJob active (status = "active")
   c. Equipment — E360 active (status in AVAIL, IN SERVICE, STANDBY)
   d. Locations — E360 all
   e. JobEquipment — HeavyJob, for each active job:
      GET /heavyjob/api/v1/jobEquipment?businessUnitId={BU}&jobId={JOB_ID}&pageSize=1000
      Store all records with isActive=true
      Note: page 2 cycles back to page 1 — only pull page 1 (1,000 records max per job)

3. Clear and replace each mirror table (in a transaction per table):
   - TRUNCATE BusinessUnit; INSERT all fetched BUs
   - TRUNCATE Job; INSERT all fetched jobs
   - TRUNCATE Equipment; INSERT all fetched equipment
   - TRUNCATE Location; INSERT all fetched locations
   - TRUNCATE JobEquipment; INSERT all fetched jobEquipment records

4. Print summary:
   - Jobs synced: N
   - Equipment synced: N
   - Locations synced: N
   - JobEquipment records synced: N
   - Duration: Xs
   - Errors: list any failures
```

### Future: Automated Scheduling (HCSS-002)

See CHANGE-REQUEST-HCSS-002-SCHEDULED-SYNC.md for cron job setup and automated scheduling.

---

## Field Mapping Reference

Columns use exact HCSS camelCase field names. Our tables are mirrors - column names match HCSS API field names exactly.

### Equipment (E360 → Supabase `Equipment` table)

| HCSS Field | Supabase Column | Notes |
|------------|-----------------|-------|
| `id` | `hcssId` | Match key for upsert |
| `businessUnitId` | `businessUnitId` | FK to BusinessUnit |
| `code` | `code` | Equipment number (cross-ref key) |
| `description` | `description` | Human-readable name |
| `equipmentType` | `equipmentType` | |
| `accountingCode` | `accountingCode` | |
| `make` | `make` | |
| `model` | `model` | |
| `year` | `year` | |
| `vin` | `vin` | |
| `serialNo` | `serialNo` | |
| `status` | `status` | AVAIL, IN SERVICE, STANDBY, DOWN |
| `enabled` | `enabled` | Y/N |
| `hourMeter` | `hourMeter` | |
| `odometer` | `odometer` | |
| `weight` | `weight` | |
| `length` | `length` | |
| `width` | `width` | |
| `height` | `height` | |
| `numberAxles` | `numberAxles` | |
| `tireSize` | `tireSize` | |
| `defaultFuel` | `defaultFuel` | |
| `purchaseDate` | `purchaseDate` | |
| `purchasePrice` | `purchasePrice` | |
| `jobCode` | `jobCode` | Current job assignment |
| `locationName` | `locationName` | Current location |
| `imageUrl` | `imageUrl` | |
| `region` | `region` | |
| `division` | `division` | |

### Jobs (HeavyJob → Supabase `Job` table)

| HCSS Field | Supabase Column | Notes |
|------------|-----------------|-------|
| `id` | `hcssId` | Match key for upsert |
| `businessUnitId` | `businessUnitId` | FK to BusinessUnit |
| `code` | `code` | Job number (cross-ref key) |
| `description` | `description` | Job name |
| `legacyId` | `legacyId` | |
| `payItemSetupType` | `payItemSetupType` | |
| `createdDate` | `createdDate` | |
| `status` | `status` | active/completed/discontinued |
| `isDeleted` | `isDeleted` | |
| `startofpayweek` | `startofpayweek` | Exact HCSS casing |
| `relatedEstimateCodes` | `relatedEstimateCodes` | jsonb array |
| `jobNote` | `jobNote` | |

### Locations (E360 → Supabase `Location` table)

| HCSS Field | Supabase Column | Notes |
|------------|-----------------|-------|
| `id` | `hcssId` | Match key for upsert |
| `businessUnitId` | `businessUnitId` | FK to BusinessUnit |
| `code` | `code` | Location code |
| `description` | `description` | Location name |
| `altCode` | `altCode` | |
| `enabled` | `enabled` | Y/N |
| `address` | `address` | jsonb - stores full address object |
| `regionCode` | `regionCode` | |
| `divisionCode` | `divisionCode` | |

---

## Migration 011: JobEquipment Table

**File:** `core/supabase/migrations/011_add_job_equipment.sql`

Creates the `JobEquipment` mirror table populated by the sync.

```sql
CREATE TABLE IF NOT EXISTS "JobEquipment" (
    "id"                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "hcssId"               uuid NOT NULL,
    "businessUnitId"       uuid,
    "businessUnitCode"     text,
    "jobHcssId"            uuid NOT NULL,
    "jobCode"              text NOT NULL,
    "equipmentHcssId"      uuid,
    "equipmentCode"        text NOT NULL,
    "equipmentDescription" text,
    "isActive"             boolean NOT NULL DEFAULT true,
    "operatorPayClassId"   uuid,
    "operatorPayClassCode" text,
    "lastSyncedAt"         timestamptz NOT NULL DEFAULT now(),
    "createdAt"            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON "JobEquipment"("equipmentCode");
CREATE INDEX ON "JobEquipment"("jobCode");
CREATE INDEX ON "JobEquipment"("jobHcssId");
CREATE INDEX ON "JobEquipment"("isActive");
```

**Note:** No `updatedAt` column — this table is truncated and rebuilt on every sync. Indexes are kept because the table is read heavily by the reconciliation engine and status indicators after each sync.

**isActive semantics:** `true` means this equipment is authorized to charge to this job. It does NOT mean the machine is physically present on site. The billing authorization list is not the deployment roster.

---

## HCSS API Authentication

**Token endpoint:** `POST https://api.hcssapps.com/identity/connect/token`
**Grant type:** `client_credentials`
**Scope:** `e360:read heavyjob:read`
**Credentials:** `HCSS_CLIENT_ID` and `HCSS_CLIENT_SECRET` (in openclaw.json)

**Critical:** All requests must include browser User-Agent header to bypass Azure WAF:
```
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
```

---

## Verification Steps — COMPLETED ✅

1. ✅ **Migration 011 applied** — `JobEquipment` table created; `Job.locationId` made nullable
2. ✅ **Dry-run verified** — Correct counts returned without writing to Supabase
3. ✅ **Full sync completed** — Supabase populated from HCSS
4. ✅ **Counts verified via direct SQL:**
   - BusinessUnit: 2
   - Equipment: 753
   - Job: 236
   - Location: 3,090
   - JobEquipment: 22,678
5. ✅ **Idempotency confirmed** — Re-running sync truncates and repopulates cleanly

**Script location:** `snc_cli/scripts/hcss_sync.py` in `github.com/james-andrew-walsh/snc-cli`
**Run command:** `python3 snc_cli/scripts/hcss_sync.py [--dry-run]`

---

## Follow-On Work (Future CRs)

- **HCSS-002:** Scheduled Sync - Automate this sync via cron (6 AM / 6 PM)
- **HCSS-003:** Telematics Snapshots - Pull GPS + engine hours from HCSS Telematics API; store as time-series
- **HCSS-004:** Geofence Entry UI - Dashboard page for humans to draw geofence boundaries on active jobs
- **HCSS-005:** CLI for Geofences and Telematics - `snc geofence`, `snc telemetry history`, `snc reconcile` commands
- **HCSS-006:** Reconciliation Engine - Compare telematics snapshots against job geofences + HeavyJob reported hours; write anomaly records

---

## Open Questions (Resolved)

1. **HCSS Client ID/Secret:** ✅ In openclaw.json as `HCSS_CLIENT_ID` and `HCSS_CLIENT_SECRET`
2. **Business unit structure:** ✅ Two BUs - E360 "Default Business Unit" and HeavyJob "Sierra Nevada Construction, Inc."
3. **Equipment360 base URL:** ✅ `https://api.hcssapps.com/e360/api/v1/`
4. **Status values:** ✅ Documented from live data - AVAIL, STANDBY, IN SERVICE, DOWN, Imported, etc.
