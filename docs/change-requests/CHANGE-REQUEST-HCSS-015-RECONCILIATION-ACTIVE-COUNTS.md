# Change Request: HCSS-015 — Reconciliation: Report Total Active Anomaly Counts

**Project:** SNC Equipment Tracking
**Date:** 2026-04-10
**Status:** READY FOR IMPLEMENTATION
**Repo:** snc-cli
**Required by:** HCSS-015b (dashboard display fix)

---

## Problem

The reconciliation Edge Function currently reports only *newly inserted* anomalies in `SyncLog.details`. On repeat runs, most anomalies already exist and are not re-inserted, so the count reads misleadingly low (e.g., "3 no HJ record" when there are actually 20 active).

---

## Fix

At the end of each reconciliation run, after inserting/resolving anomalies, query the `Anomaly` table for total active counts by type (`WHERE resolvedAt IS NULL`) and write them to `SyncLog.details`.

---

## Change: reconciliation/index.ts

After all inserts and resolves are complete, add:

```typescript
// Query total active anomaly counts
const { data: activeCounts } = await supabase
  .from('Anomaly')
  .select('anomalyType')
  .is('resolvedAt', null);

const totalActive = activeCounts?.length ?? 0;
const activeNoHj = activeCounts?.filter(a => a.anomalyType === 'ANOMALY_NO_HJ').length ?? 0;
const activeDisputed = activeCounts?.filter(a => a.anomalyType === 'DISPUTED').length ?? 0;
const activeNotInEither = activeCounts?.filter(a => a.anomalyType === 'NOT_IN_EITHER').length ?? 0;

// Write to SyncLog details:
details: {
  // New this run
  new_anomalies: newAnomalies.length,
  resolved: resolvedCount,
  // Total currently active (what operators should see)
  total_active: totalActive,
  anomaly_no_hj: activeNoHj,
  disputed: activeDisputed,
  not_in_either: activeNotInEither,
}
```

---

## No Migration Required

No schema changes — `details` jsonb column already exists from migration 020.

---

## Deployment

Deploy updated reconciliation function only:
```
cd core
supabase functions deploy reconciliation --project-ref ghscnwwatguzmeuabspd
```

## Verification

Trigger the reconciliation function. Query SyncLog:
```
curl "https://ghscnwwatguzmeuabspd.supabase.co/rest/v1/SyncLog?select=details&providerKey=eq.reconciliation&order=completedAt.desc&limit=1"
```
Should show `total_active`, `anomaly_no_hj`, `disputed`, `not_in_either` with accurate totals matching the Anomaly table `WHERE resolvedAt IS NULL`.

Commit: "feat: HCSS-015 — reconciliation reports total active anomaly counts in SyncLog details"
Push to GitHub.
When completely finished, run: openclaw system event --text "Done: HCSS-015 reconciliation active counts implemented" --mode now
