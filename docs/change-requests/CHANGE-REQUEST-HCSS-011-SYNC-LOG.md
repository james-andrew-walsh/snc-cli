# Change Request: HCSS-011 — Sync Log Table + Edge Function Logging

**Project:** SNC Equipment Tracking
**Date:** 2026-04-10
**Status:** READY FOR IMPLEMENTATION
**Repo:** snc-cli
**Depends on:** HCSS-010 (telemetrics Edge Function)
**Required by:** HCSS-012 (dashboard sync log display)

---

## Summary

Add a `SyncLog` table to record every sync run across all providers. Update the `telemetrics-sync` Edge Function to write a row to `SyncLog` at the end of each provider's sync. This gives operators visibility into when syncs ran, how many records were processed, and whether any errors occurred.

The `SyncLog` table is subscribed to via Supabase Realtime by the dashboard (HCSS-012), so new sync entries appear in the Recent Activity panel without polling.

---

## Migration 018: SyncLog Table

File: `core/supabase/migrations/018_add_sync_log.sql`

```sql
CREATE TABLE IF NOT EXISTS "SyncLog" (
    "id"            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "providerKey"   text NOT NULL,           -- "e360", "jdlink", "visionlink", etc.
    "providerName"  text NOT NULL,           -- Human-readable: "Equipment360 (HCSS)"
    "status"        text NOT NULL,           -- "success" | "error"
    "rowsInserted"  integer,                 -- number of TelematicsSnapshot rows written
    "durationMs"    integer,                 -- wall-clock duration of this provider's sync
    "errorMessage"  text,                    -- populated if status = "error"
    "startedAt"     timestamptz NOT NULL,
    "completedAt"   timestamptz NOT NULL DEFAULT now(),
    "createdAt"     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON "SyncLog"("providerKey");
CREATE INDEX ON "SyncLog"("completedAt" DESC);
CREATE INDEX ON "SyncLog"("status");

-- Enable Realtime for dashboard subscription
ALTER PUBLICATION supabase_realtime ADD TABLE "SyncLog";
```

---

## Edge Function Update: telemetrics-sync/index.ts

After each provider's `sync()` call completes (success or error), insert a row into `SyncLog`:

```typescript
// After provider.sync() resolves or rejects:
await supabase.from('SyncLog').insert({
  providerKey: provider.providerKey,
  providerName: providerRow.name,
  status: error ? 'error' : 'success',
  rowsInserted: snapshots.length,
  durationMs: Date.now() - providerStartTime,
  errorMessage: error?.message ?? null,
  startedAt: new Date(providerStartTime).toISOString(),
  completedAt: new Date().toISOString(),
});
```

The insert uses the service role key so it bypasses RLS. If the SyncLog insert itself fails, log to console but do not throw — a logging failure must never break the sync.

---

## Files to Create

| File | Description |
|------|-------------|
| `core/supabase/migrations/018_add_sync_log.sql` | SyncLog table + indexes + Realtime publication |

## Files to Modify

| File | Change |
|------|--------|
| `core/supabase/functions/telemetrics-sync/index.ts` | Add SyncLog insert after each provider run |

---

## Verification Steps

1. Apply migration 018 to Supabase
2. Deploy updated Edge Function: `supabase functions deploy telemetrics-sync --project-ref ghscnwwatguzmeuabspd` (run from `core/` directory)
3. Trigger the function manually from the Supabase dashboard
4. Query `SyncLog` — confirm a row exists with `providerKey = "e360"`, `status = "success"`, `rowsInserted ≈ 610`
5. Confirm `SyncLog` appears in Supabase Realtime publications

After verifying, HCSS-012 (dashboard) can be implemented.
