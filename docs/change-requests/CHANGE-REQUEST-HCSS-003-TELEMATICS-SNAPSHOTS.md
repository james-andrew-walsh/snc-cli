# Change Request: HCSS-003 — Telematics Snapshots

**Project:** SNC Equipment Tracking  
**Date:** 2026-04-08
**Updated:** 2026-04-09  
**Status:** READY FOR IMPLEMENTATION  
**Depends on:** HCSS-001 ✅ (complete)

---

## Summary

Pull GPS coordinates and engine hours from the HCSS Telematics API and store them as a time-series in a `TelematicsSnapshot` table. This is the machine-verified ground truth layer — the data we compare against HeavyJob human-reported hours and job geofences.

---

## The Problem This Solves

HCSS Telematics provides the current position and engine hours for each registered machine (468 registered, 131 engine-active as of 2026-04-08). But the API only gives us the **latest** reading — it does not provide historical snapshots.

To answer reconciliation questions like "did this machine run 8 hours at job 11062 today?", we need to store readings over time so we can compute deltas:
- Engine hours delta = (today's reading - yesterday's reading)
- Location at each reading = GPS coordinates

---

## Schema Changes

### New Table: `TelematicsSnapshot` (value-add — never wiped)

```sql
CREATE TABLE IF NOT EXISTS "TelematicsSnapshot" (
    "id"                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "equipmentCode"               text NOT NULL,
    "equipmentHcssId"             uuid,
    "latitude"                    double precision,
    "longitude"                   double precision,
    "locationDateTime"            timestamptz,
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
```

**Why append-only:** Each row is a point-in-time reading. We never update or delete rows. The delta between two rows for the same equipment tells us engine activity and location over that interval.

**GPS staleness (confirmed 2026-04-09):** The HCSS Telematics API returns a `lastLocationDateTime` field, but the date portion alone is insufficient. Live testing showed a machine with a `lastLocationDateTime` that appeared to be "today" but whose UTC timestamp was from the previous evening (~13 hours prior). The raw UTC timestamp must be stored and compared. Any GPS position older than a configurable threshold (suggested: 4 hours) should be flagged as stale and excluded from reconciliation decisions. Never treat `lastLocationDateTime` as reliable without checking the full timestamp.

---

## Sync Script: `snc_cli/scripts/hcss_telematics_sync.py`

Standalone script, same pattern as `hcss_sync.py`. CLI promotion comes later.

**Logic:**
```
1. Get HCSS OAuth2 token (scope: telematics:read)

2. GET /telematics/api/v1/equipment (paginated)
   - Returns: code, lastLatitude, lastLongitude, lastLocationDateTime,
              lastHourMeterReadingInHours, lastHourMeterReadingDateTime,
              lastHourMeterReadingSource, lastEngineStatus, lastEngineStatusDateTime

3. For each equipment record:
   - Look up equipmentHcssId from our Equipment table by code
   - Insert row into TelematicsSnapshot
   - Do NOT upsert — always insert (time-series, every reading is a new row)

4. Print summary:
   - Snapshots recorded: N
   - Errors: list any failures
```

---

## Sync Frequency

Twice daily at same time as HCSS-001 core sync (6 AM / 6 PM via HCSS-002).

With twice-daily snapshots we can compute:
- Morning engine hours delta (6 PM yesterday → 6 AM today) — overnight running
- Day engine hours delta (6 AM → 6 PM) — working hours
- Location at each snapshot

For the "half day at location A, half day at location B" case: two snapshots per day is not perfect, but will catch mid-day moves. Can increase frequency if needed later.

---

## Key Data From Live API (verified 2026-04-08)

Example record for equipment 7762 ("21 JD 210L SKIP LOADER"):
```json
{
  "code": "7762",
  "lastLatitude": 39.455167,
  "lastLongitude": -119.794083,
  "lastLocationDateTime": "2026-04-08T18:54:07Z",
  "lastHourMeterReadingInHours": 3326.35,
  "lastHourMeterReadingDateTime": "2026-04-08T18:53:36Z",
  "lastHourMeterReadingSource": "OEM Data with Offset",
  "lastEngineStatus": "Active",
  "lastEngineStatusDateTime": "2026-03-06T22:53:10Z"
}
```

585 of 610 telematics records have GPS data. 131 show active engine status.

---

## Verification Steps

1. Apply `TelematicsSnapshot` table migration
2. Run telematics sync: `snc sync hcss --telematics`
3. Verify rows inserted via direct SQL: `SELECT COUNT(*) FROM "TelematicsSnapshot"`
4. Run sync again — verify new rows are APPENDED (row count increases, not stays same)
5. Verify GPS staleness flag: check that machines with `lastLocationDateTime` > 4 hours ago are flagged
6. Spot-check one equipment: confirm latitude/longitude are plausible Reno-area coordinates

---

## Follow-On Work

- HCSS-005: CLI commands for querying snapshot history
- HCSS-006: Reconciliation engine uses snapshots + geofences
