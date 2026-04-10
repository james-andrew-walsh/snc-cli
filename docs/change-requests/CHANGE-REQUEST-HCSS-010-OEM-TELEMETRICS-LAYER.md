# Change Request: HCSS-010 — OEM Telemetrics Provider Layer

**Project:** SNC Equipment Tracking
**Date:** 2026-04-10
**Status:** READY FOR IMPLEMENTATION
**Repo:** snc-cli
**Depends on:** HCSS-001 (sync layer), HCSS-003 (telematics snapshots)

---

## Summary

Migrate the telematics sync from a one-off Python script (`hcss_sync.py`) to a production-grade, multi-provider architecture. E360 is the first concrete provider. The infrastructure is built to accept JDLink, VisionLink (Cat), and MyKomatsu as additional providers with minimal changes.

A Supabase Edge Function runs on a 3-hour cron schedule and iterates all enabled providers, calling each provider's sync function and inserting normalized `TelematicsSnapshot` rows into Supabase.

**Nyquist rationale for 3-hour interval:** HCSS E360 telematics updates the hour meter on ~6-hour intervals. To guarantee we capture every update, we sample at half that interval (3 hours). OEM platforms (JDLink, VisionLink) may have finer-grained data; the 3-hour cadence is a safe floor for all providers.

---

## Background: Why This CR Exists

Andy (SNC) confirmed in the April 9 meeting:
- E360/HCSS telematics gives GPS and engine on/off, but NOT idle vs. productive hours
- Idle vs. productive distinction requires the OEM manufacturer platforms: Cat VisionLink, JD JDLink, Komatsu MyKomatsu
- These platforms are already in use at SNC — Andy manually pulls them weekly
- The data is all there; it just requires automation

The current `hcss_telematics_sync.py` script is Python, runs manually, and is not multi-provider. This CR replaces it with a scheduled, extensible Edge Function.

---

## Architecture

### TelematicsProvider Registry (database)

A `TelematicsProvider` table in Supabase stores registered providers. New providers are added by inserting a row — no code deployment required to enable/disable.

```
TelematicsProvider
  id          uuid PK
  name        text          -- "E360", "JDLink", "VisionLink", "MyKomatsu"
  providerKey text UNIQUE   -- "e360", "jdlink", "visionlink", "mykomatsu"
  enabled     boolean       -- toggle without deploying code
  config      jsonb         -- provider-specific auth config (credentials, org IDs, etc.)
  createdAt   timestamptz
  updatedAt   timestamptz
```

### TelematicsSnapshot — add providerKey column

Existing `TelematicsSnapshot` table gets one new column:

```
providerKey  text   -- which provider produced this row; null = legacy E360 rows
```

This allows queries to distinguish E360 readings from JDLink readings for the same machine, and to prefer the more precise source when both are available.

### Edge Function: telemetrics-sync

Location: `core/supabase/functions/telemetrics-sync/index.ts`

Responsibilities:
1. Query `TelematicsProvider` for all rows where `enabled = true`
2. For each provider, call the provider's `sync()` function
3. Each provider's sync function fetches data from the external API and returns an array of normalized snapshot objects
4. Insert all snapshot rows into `TelematicsSnapshot` (append-only, same as current behavior)
5. Log sync results (provider, row count, any errors) to console

### Provider Interface (TypeScript)

```typescript
interface OEMTelematicsProvider {
  providerKey: string;
  sync(config: Record<string, unknown>): Promise<TelematicsSnapshotInsert[]>;
}

interface TelematicsSnapshotInsert {
  equipmentCode: string;
  equipmentHcssId?: string;
  latitude?: number;
  longitude?: number;
  locationDateTime?: string;
  isLocationStale: boolean;
  hourMeterReadingInHours?: number;
  hourMeterReadingDateTime?: string;
  hourMeterReadingSource?: string;
  engineStatus?: string;  // "ON" | "OFF" | "IDLE" | "UNKNOWN"
  engineStatusDateTime?: string;
  idleHours?: number;       // OEM-only field; null for E360
  productiveHours?: number; // OEM-only field; null for E360
  providerKey: string;
  snapshotAt: string;
}
```

### E360 Provider (TypeScript port of hcss_telematics_sync.py)

Port the existing Python telematics sync logic to TypeScript:

1. Authenticate against HCSS using `HCSS_CLIENT_ID` / `HCSS_CLIENT_SECRET` (client credentials OAuth2)
2. Fetch all telematics records from E360: `GET /e360/api/v1/equipment/telematics?businessUnitId={BU}`
3. For each record: extract equipment code, GPS lat/lon, location timestamp, hour meter, engine status
4. Compute `isLocationStale`: true if `locationDateTime` is more than 4 hours old
5. Return normalized `TelematicsSnapshotInsert[]` with `providerKey = "e360"`

HCSS auth token endpoint: `POST https://identityqa.hcssapps.com/connect/token`
E360 telematics endpoint: `GET https://api.hcssapps.com/e360/api/v1/equipment/telematics`

Credentials from environment variables (already in Supabase secrets):
- `HCSS_CLIENT_ID`
- `HCSS_CLIENT_SECRET`

### Cron Schedule (config.toml)

Add to `core/supabase/config.toml`:

```toml
[functions.telemetrics-sync]
enabled = true

[[functions.telemetrics-sync.schedules]]
cron = "0 */3 * * *"
```

This fires the Edge Function at 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 UTC daily.

---

## Migration 017: TelematicsProvider table + providerKey column

File: `core/supabase/migrations/017_add_telemetrics_provider.sql`

```sql
-- TelematicsProvider registry
CREATE TABLE IF NOT EXISTS "TelematicsProvider" (
    "id"          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "name"        text NOT NULL,
    "providerKey" text NOT NULL UNIQUE,
    "enabled"     boolean NOT NULL DEFAULT true,
    "config"      jsonb NOT NULL DEFAULT '{}',
    "createdAt"   timestamptz NOT NULL DEFAULT now(),
    "updatedAt"   timestamptz NOT NULL DEFAULT now()
);

-- Add providerKey to TelematicsSnapshot
ALTER TABLE "TelematicsSnapshot"
    ADD COLUMN IF NOT EXISTS "providerKey" text,
    ADD COLUMN IF NOT EXISTS "idleHours" double precision,
    ADD COLUMN IF NOT EXISTS "productiveHours" double precision;

CREATE INDEX IF NOT EXISTS ON "TelematicsSnapshot"("providerKey");

-- Seed E360 as the first provider
INSERT INTO "TelematicsProvider" ("name", "providerKey", "enabled", "config")
VALUES ('Equipment360 (HCSS)', 'e360', true, '{}')
ON CONFLICT ("providerKey") DO NOTHING;
```

---

## Files to Create

| File | Description |
|------|-------------|
| `core/supabase/migrations/017_add_telemetrics_provider.sql` | Migration for provider table + snapshot columns |
| `core/supabase/functions/telemetrics-sync/index.ts` | Edge Function entry point (iterates providers) |
| `core/supabase/functions/telemetrics-sync/providers/e360.ts` | E360 provider (TypeScript port of Python script) |
| `core/supabase/functions/telemetrics-sync/types.ts` | Shared TypeScript interfaces |

## Files to Modify

| File | Change |
|------|--------|
| `core/supabase/config.toml` | Add `[functions.telemetrics-sync]` cron schedule section |
| `snc_cli/scripts/hcss_telematics_sync.py` | Mark as deprecated with comment pointing to Edge Function |

---

## Files to Retire

`snc_cli/scripts/hcss_telematics_sync.py` — superseded by Edge Function. Keep in repo with deprecation notice; do not delete until Edge Function is verified in production.

---

## Future Providers (not in scope for this CR)

Once James has credentials provisioned on JDLink, VisionLink, and MyKomatsu:

- Each new provider is a new file: `providers/jdlink.ts`, `providers/visionlink.ts`, `providers/mykomatsu.ts`
- JDLink auth: OAuth 2 authorization code flow (user-delegated), token stored in `TelematicsProvider.config`
- VisionLink (Cat): similar OAuth flow via Caterpillar API
- MyKomatsu: similar OAuth flow
- Register each in the `TelematicsProvider` table with `enabled = true`
- The Edge Function picks them up automatically on next run

JDLink-specific notes from API docs:
- Scope required: `eq1` (View Equipment)
- Key endpoints: `GET /machines/{principalId}/engineHours`, `GET /machines/{principalId}/hoursOfOperation`
- `hoursOfOperation` returns on/off durations for a time range — this is the idle vs. productive signal
- Access token expires after 12 hours; refresh token valid 365 days
- Machine IDs (principalId) will require a one-time mapping step against SNC equipment codes

---

## Verification Steps

1. Run migration 017 against Supabase — confirm `TelematicsProvider` table created, `e360` row seeded
2. Deploy Edge Function locally (`supabase functions serve telemetrics-sync`)
3. Trigger manually — confirm E360 sync runs and inserts rows with `providerKey = "e360"`
4. Confirm `TelematicsSnapshot` row count increases by ~610 per run (same as Python script)
5. Confirm `isLocationStale` logic matches Python script output
6. Deploy to Supabase (`supabase functions deploy telemetrics-sync`)
7. Confirm cron fires at next 3-hour boundary
8. Verify rows appear in Supabase with correct timestamps
