# HCSS-017A: Telemetrics Engine Timestamp (Backend)

## Problem
The OEM telematics API reports engine status as "Active", but that status can be days or weeks old (e.g., stuck on March 18th). We need to capture the timestamp of the last engine status report so the frontend can display it, preventing stale data from looking like a live running engine.

## Implementation Details

### Database Migration
- Add `engineStatusAt` (timestamptz) to the `TelematicsSnapshot` table.
- Create a migration file in `core/supabase/migrations/`.

### Sync Logic Update
- Update the Edge Function (`core/supabase/functions/telemetrics-sync/providers/e360.ts`).
- Extract `lastEngineStatusDateTime` from the API payload and map it to the new `engineStatusAt` column during insert.

## Dependencies
- None. Can be implemented immediately.
