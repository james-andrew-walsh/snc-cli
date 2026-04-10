# Change Request: HCSS-013 — Persistent Reconciliation Engine

**Project:** SNC Equipment Tracking
**Date:** 2026-04-10
**Status:** READY FOR IMPLEMENTATION
**Repos:** snc-cli (primary), snc-dashboard (secondary — separate CR HCSS-013b)
**Depends on:** HCSS-010 (telemetrics Edge Function), HCSS-011 (SyncLog)

---

## Summary

Replace the on-demand PostGIS RPC (`get_reconciliation_status()`) with a persistent reconciliation engine that runs automatically after every telemetrics sync, writes results to an `Anomaly` table, and logs a summary to `SyncLog`.

This architecture is designed to grow. Current checks (geofence + HeavyJob authorization) are the first two rules. Future checks (idle hours, time card comparison, provider cross-validation) are added as new code paths in the same Edge Function — no schema changes required.

---

## Background: Current vs. Target Architecture

**Current:**
- Dashboard calls `get_reconciliation_status()` RPC on page load
- RPC runs ST_Within + joins in real time
- Results are never stored — recomputed on every load
- No history, no scheduling, no extensibility

**Target:**
- `reconciliation` Edge Function runs after every telemetrics sync
- Writes results to `Anomaly` table (persistent, queryable)
- Logs a summary row to `SyncLog`
- Dashboard reads from `Anomaly` table — no live RPC call
- New reconciliation rules = new code in the Edge Function, not schema changes

---

## Migration 019: Anomaly Table

File: `core/supabase/migrations/019_add_anomaly_table.sql`

```sql
-- Drop and replace any existing Anomaly table stub
DROP TABLE IF EXISTS "Anomaly";

CREATE TABLE "Anomaly" (
    "id"                uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    "equipmentCode"     text NOT NULL,
    "equipmentHcssId"   uuid,
    "siteLocationId"    uuid REFERENCES "SiteLocation"("id") ON DELETE SET NULL,

    -- Classification
    "anomalyType"       text NOT NULL,
    -- Current types:
    --   ANOMALY_NO_HJ      — E360 assigns here, HeavyJob has no authorization record
    --   DISPUTED           — E360 and HeavyJob disagree on job code
    --   NOT_IN_EITHER      — engine active, GPS on site, no record in E360 or HJ
    --   HOURS_MISMATCH     — (future) GPS engine hours don't match time card
    --   IDLE_THRESHOLD     — (future) machine idle > X% of reported hours
    --   PROVIDER_DISAGREE  — (future) E360 and JDLink report different hours
    "severity"          text NOT NULL DEFAULT 'warning',
    -- "warning" | "error" | "info"

    -- Context (populated at detection time)
    "e360JobCode"       text,
    "e360LocationName"  text,
    "hjJobCode"         text,
    "hjJobDescription"  text,
    "engineStatus"      text,
    "hourMeter"         double precision,
    "latitude"          double precision,
    "longitude"         double precision,

    -- Lifecycle
    "detectedAt"        timestamptz NOT NULL DEFAULT now(),
    "resolvedAt"        timestamptz,            -- null = still active
    "reconciliationRunId" uuid,                 -- links to the SyncLog entry that found this

    "createdAt"         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON "Anomaly"("equipmentCode");
CREATE INDEX ON "Anomaly"("siteLocationId");
CREATE INDEX ON "Anomaly"("anomalyType");
CREATE INDEX ON "Anomaly"("detectedAt" DESC);
CREATE INDEX ON "Anomaly"("resolvedAt") WHERE "resolvedAt" IS NULL;

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE "Anomaly";
```

---

## New Edge Function: reconciliation

Location: `core/supabase/functions/reconciliation/index.ts`

### Inputs
Called via HTTP POST by `telemetrics-sync` after sync completes. No body required.

### Logic

```
1. Load all active SiteLocations with their associated job codes (SiteLocation + SiteLocationJob)
2. Load the most recent TelematicsSnapshot per equipment code (latest snapshotAt per code)
3. Load all JobEquipment records (the HeavyJob billing authorization list)
4. Load all Equipment records (E360 current job assignment)

5. For each SiteLocation:
   a. Find all TelematicsSnapshot rows where GPS is within the SiteLocation geofence
      (ST_Within on the geom column)
   b. For each machine inside the geofence:
      - Get E360 job code (from Equipment.jobCode)
      - Get HJ authorization (does a JobEquipment row exist for this machine + any job
        associated with this SiteLocation?)
      - Classify:
          OK              → E360 job matches a SiteLocation job AND HJ has authorization
          ANOMALY_NO_HJ   → E360 assigns here, no HJ authorization record
          DISPUTED        → HJ and E360 disagree on which job
          NOT_IN_EITHER   → engine active, inside geofence, not in E360 or HJ for this site

6. Mark previously-detected anomalies that are no longer present as resolved
   (set resolvedAt = now() where equipmentCode + siteLocationId no longer appear in results)

7. Insert new anomaly rows for newly detected anomalies

8. Write a SyncLog entry:
   {
     providerKey: "reconciliation",
     providerName: "Reconciliation Engine",
     status: "success" | "error",
     rowsInserted: <number of new anomalies>,
     durationMs: <wall clock>,
     errorMessage: null | <error>
   }
```

### Future check stubs (implement as no-ops now, flesh out later)
```typescript
// HOURS_MISMATCH: compare TelematicsSnapshot hourMeter delta vs time card hours
// Stub: log intent, skip — time card data not yet available
async function checkHoursMismatch(...) { return []; }

// IDLE_THRESHOLD: check if idleHours / totalHours > threshold
// Stub: log intent, skip — OEM idle data not yet available
async function checkIdleThreshold(...) { return []; }

// PROVIDER_DISAGREE: compare E360 and JDLink readings for same machine
// Stub: log intent, skip — JDLink not yet provisioned
async function checkProviderDisagreement(...) { return []; }
```

---

## Update: telemetrics-sync/index.ts

After all providers sync successfully, invoke the reconciliation function:

```typescript
// At end of telemetrics-sync, after SyncLog insert:
const reconciliationUrl = `${Deno.env.get('SUPABASE_URL')}/functions/v1/reconciliation`;
await fetch(reconciliationUrl, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')}`,
    'Content-Type': 'application/json',
  },
  body: '{}',
}).catch(err => console.error('Failed to trigger reconciliation:', err));
// Non-blocking: catch and log but do not throw
```

---

## Files to Create

| File | Description |
|------|-------------|
| `core/supabase/migrations/019_add_anomaly_table.sql` | Anomaly table with full schema |
| `core/supabase/functions/reconciliation/index.ts` | Reconciliation Edge Function |

## Files to Modify

| File | Change |
|------|--------|
| `core/supabase/functions/telemetrics-sync/index.ts` | Invoke reconciliation after sync completes |

## Files NOT to Touch
`get_reconciliation_status()` RPC — keep in place as a debugging/fallback tool. Dashboard migration to read from Anomaly table is handled in HCSS-013b (snc-dashboard).

---

## Verification Steps

1. Apply migration 019
2. Deploy both Edge Functions: `supabase functions deploy reconciliation` and `supabase functions deploy telemetrics-sync` (from `core/` directory)
3. Trigger `telemetrics-sync` manually from Supabase dashboard
4. Confirm `reconciliation` was triggered automatically (check Supabase function logs)
5. Query `Anomaly` table — confirm rows exist with correct `anomalyType` values
6. Compare anomaly count against previous `get_reconciliation_status()` output — should match (22 ANOMALY, 2 DISPUTED, 1 NOT_IN_EITHER for West 4th Street)
7. Query `SyncLog` — confirm two entries: one for E360 sync, one for reconciliation
8. Trigger a second time — confirm previously-active anomalies are NOT duplicated, and resolved anomalies get `resolvedAt` populated
