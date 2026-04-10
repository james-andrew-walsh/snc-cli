# Change Request: HCSS-014 — SyncLog Details Field

**Project:** SNC Equipment Tracking
**Date:** 2026-04-10
**Status:** READY FOR IMPLEMENTATION
**Repo:** snc-cli
**Required by:** HCSS-014b (dashboard display)

---

## Summary

Add a `details` jsonb column to `SyncLog` so sync runs can report structured metadata beyond just row count. Update the E360 provider and reconciliation Edge Function to populate it.

---

## Migration 020: Add details column to SyncLog

File: `core/supabase/migrations/020_add_sync_log_details.sql`

```sql
ALTER TABLE "SyncLog"
    ADD COLUMN IF NOT EXISTS "details" jsonb;
```

---

## E360 Provider Update (telemetrics-sync)

In `core/supabase/functions/telemetrics-sync/providers/e360.ts` or `index.ts`, count fresh vs. stale GPS at sync time and pass to SyncLog:

```typescript
// Count stale vs fresh from the snapshots array
const staleCount = snapshots.filter(s => s.isLocationStale).length;
const freshCount = snapshots.length - staleCount;

// In the SyncLog insert, add details:
details: {
  total: snapshots.length,
  fresh_gps: freshCount,
  stale_gps: staleCount,
}
```

---

## Reconciliation Engine Update

In `core/supabase/functions/reconciliation/index.ts`, count anomalies by type and pass to SyncLog:

```typescript
const anomalyNoHj = newAnomalies.filter(a => a.anomalyType === 'ANOMALY_NO_HJ').length;
const disputed = newAnomalies.filter(a => a.anomalyType === 'DISPUTED').length;
const notInEither = newAnomalies.filter(a => a.anomalyType === 'NOT_IN_EITHER').length;

// In the SyncLog insert, add details:
details: {
  anomaly_no_hj: anomalyNoHj,
  disputed: disputed,
  not_in_either: notInEither,
  resolved: resolvedCount,
}
```

---

## Files to Create

| File | Description |
|------|-------------|
| `core/supabase/migrations/020_add_sync_log_details.sql` | Add details jsonb column to SyncLog |

## Files to Modify

| File | Change |
|------|--------|
| `core/supabase/functions/telemetrics-sync/index.ts` or `providers/e360.ts` | Add details to SyncLog insert |
| `core/supabase/functions/reconciliation/index.ts` | Add details to SyncLog insert |

---

## Deployment

Apply migration 020, then deploy both updated Edge Functions:
```
cd core
supabase functions deploy telemetrics-sync --project-ref ghscnwwatguzmeuabspd
supabase functions deploy reconciliation --project-ref ghscnwwatguzmeuabspd
```

## Verification

Trigger telemetrics-sync manually. Query SyncLog:
```
curl "https://ghscnwwatguzmeuabspd.supabase.co/rest/v1/SyncLog?select=providerKey,rowsInserted,details&order=completedAt.desc&limit=4"
```
Should see `details` populated with `{total, fresh_gps, stale_gps}` for E360 and `{anomaly_no_hj, disputed, not_in_either, resolved}` for reconciliation.

Commit: "feat: HCSS-014 — SyncLog details field (fresh/stale GPS + anomaly breakdown)"
Push to GitHub.
When completely finished, run: openclaw system event --text "Done: HCSS-014 SyncLog details implemented and deployed" --mode now
