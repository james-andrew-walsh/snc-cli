# Change Request: HCSS-006 — Reconciliation Engine

**Project:** SNC Equipment Tracking  
**Date:** 2026-04-08  
**Updated:** 2026-04-09  
**Status:** DRAFT  
**Depends on:** HCSS-001 (jobs + jobEquipment cache), HCSS-003 (telematics snapshots), HCSS-004 (SiteLocation + SiteLocationJob), HCSS-005 (CLI)

---

## Summary

Build the reconciliation engine that compares three data sources — telematics GPS (where machines actually are), job geofences (where they should be), and HeavyJob reported hours (what was claimed) — and writes anomaly records when they disagree. This is the core value of the system.

---

## The Three Questions

For each piece of GPS-tracked equipment, the engine answers:

1. **Location:** Is the machine inside a geofence associated with any job it is authorized to charge to? (telematics GPS vs `SiteLocation` polygon + `SiteLocationJob` mapping)
2. **Activity:** Was the machine running? (engine hours delta > 0 between telematics snapshots)
3. **Hours:** Do the reported hours match actual hours? (HeavyJob time card delta vs telematics hour meter delta)

**Key design point (2026-04-09):** The reconciliation unit is the machine + location, not machine + job. A machine is correctly placed if it is inside any geofence whose location is associated with any job the machine is authorized to charge to. This handles the one-site/multiple-job-codes pattern.

---

## Anomaly Types

| Type | Trigger | Severity | Meaning |
|------|---------|----------|---------|
| `location_mismatch` | Machine GPS outside job geofence at time of snapshot | WARNING | Machine not at its assigned job site |
| `idle_rental` | Rental with 0 engine hours for N+ days | CRITICAL | Rental sitting idle, billing daily |
| `hours_discrepancy` | HeavyJob reported hours differ from telematics by >1hr | WARNING | Potential billing error or data entry error |
| `no_geofence` | Job has active equipment but no geofence set | INFO | Cannot check location until geofence is added |
| `ghost_operation` | Engine hours accumulating on machine with no active job assignment | WARNING | Machine running somewhere untracked |

---

## Schema Changes

### New Table: `ReconciliationRun` (value-add — never wiped)

```sql
CREATE TABLE IF NOT EXISTS "ReconciliationRun" (
    "id"            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "ranAt"         timestamptz NOT NULL DEFAULT now(),
    "jobsChecked"   integer,
    "equipmentChecked" integer,
    "anomaliesFound" integer,
    "triggeredBy"   text  -- 'cron', 'manual', 'agent'
);
```

### New Table: `Anomaly` (value-add — never wiped)

```sql
CREATE TABLE IF NOT EXISTS "Anomaly" (
    "id"                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "runId"               uuid REFERENCES "ReconciliationRun"("id"),
    "type"                text NOT NULL,
    "severity"            text NOT NULL,  -- CRITICAL, WARNING, INFO
    "jobCode"             text,
    "jobHcssId"           uuid,
    "equipmentCode"       text,
    "equipmentHcssId"     uuid,
    "description"         text NOT NULL,
    "detectedAt"          timestamptz NOT NULL DEFAULT now(),
    "resolvedAt"          timestamptz,
    "resolvedBy"          uuid REFERENCES "user_profiles"("id"),
    "resolutionNote"      text,
    "data"                jsonb
);

CREATE INDEX ON "Anomaly"("type");
CREATE INDEX ON "Anomaly"("severity");
CREATE INDEX ON "Anomaly"("jobCode");
CREATE INDEX ON "Anomaly"("equipmentCode");
CREATE INDEX ON "Anomaly"("detectedAt");
```

---

## Reconciliation Script: `snc_cli/scripts/reconcile.py`

Or extend `snc_cli` with `snc reconcile run`.

**Logic:**
```
1. Load all SiteLocations that have at least one job and a geofence polygon
2. For each tracked machine (equipment with a TelematicsSnapshot in last 24h):
   a. Check GPS staleness — if last snapshot >4 hours old, skip location check, write stale_gps INFO
   b. Determine which SiteLocation(s) the machine is inside (point-in-polygon test)
   c. Determine which jobs the machine is authorized to charge to:
      - HeavyJob: JobEquipmentCache records where equipmentCode matches and isActive=true
      - E360: equipment.jobCode field
   d. Cross-check: for each SiteLocation the machine is inside,
      does that location have any job the machine is authorized to charge to?
      - YES → machine is correctly placed ✅
      - NO  → location_mismatch ⚠️ (machine is on site but assigned to a different location)
   e. If machine is NOT inside any geofence:
      - Has active job assignments → machine is away from its job site ⚠️
      - Has no job assignments → ghost_operation if engine hours accumulating ⚠️
   f. Compute hour meter delta between last two snapshots
   g. If rental and hour delta = 0 for 3+ days → idle_rental CRITICAL

3. Load SiteLocations with no geofence → write no_geofence INFO for each
4. Write ReconciliationRun record with summary counts
5. Print anomaly summary
```

---

## Running the Engine

**Manual:** `snc reconcile run`  
**Automated:** Run after each sync (add to cron after HCSS-002 — sync then reconcile)  
**On-demand for one job:** `snc reconcile run --job 11062`

---

## Dashboard Changes

### Anomaly Feed on Overview Page

Add anomaly panel to the Overview dashboard:
- Count badges: CRITICAL (red), WARNING (yellow), INFO (blue)
- List of recent anomalies, most severe first
- Click anomaly to see detail: job, equipment, what the discrepancy is, when detected
- "Mark Resolved" button with optional note

### Equipment View

Add "Anomalies" column — shows anomaly count per machine, colored by worst severity.

---

## Verification Steps

1. Apply `ReconciliationRun` and `Anomaly` table migrations
2. Set a geofence for at least one job (HCSS-004)
3. Run telematics sync to get snapshots (HCSS-003)
4. Run reconciliation: `snc reconcile run`
5. Verify: `snc reconcile list` shows anomalies
6. Verify: `snc reconcile list --severity critical` filters correctly
7. Verify anomaly feed appears on dashboard Overview page
8. Mark one anomaly resolved, verify `resolvedAt` is set

---

## Follow-On Work

- Alerting: Push critical anomalies to Telegram (via OpenClaw)
- Agent: OpenClaw agent queries `snc reconcile list --severity critical` on a schedule and narrates findings
- Trend analysis: Track anomaly rates over time per job and equipment
