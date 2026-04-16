# CHANGE REQUEST: Update get_latest_telematics for Multi-Provider Support

## Overview
The `get_latest_telematics` RPC currently uses `DISTINCT ON (t."equipmentCode")` without distinguishing by provider. Because JDLink snapshots often arrive seconds after HCSS snapshots, the JDLink snapshot becomes the single "latest" row for that equipment, entirely omitting the HCSS data from the result set. This breaks the dashboard's provider filtering and comparison mode.

## Technical Details
- **Target:** `core/supabase/migrations/024_fix_rpc_multi_provider.sql`
- **Current Behavior:** `DISTINCT ON (t."equipmentCode")`
- **Required Behavior:** `DISTINCT ON (t."equipmentCode", t."providerKey")`
- **Result:** The RPC will return the latest snapshot *per equipment, per provider*, allowing the dashboard to group them by equipment code and compute discrepancies properly.

## Implementation Steps
1. Create migration `024_fix_rpc_multi_provider.sql` with the updated RPC definition.
2. Ensure the `ORDER BY` clause is updated to match: `ORDER BY t."equipmentCode", t."providerKey", t."snapshotAt" DESC`
3. Apply migration to the Supabase instance.
4. Verify using the CLI `telemetry compare` command and the dashboard UI.
