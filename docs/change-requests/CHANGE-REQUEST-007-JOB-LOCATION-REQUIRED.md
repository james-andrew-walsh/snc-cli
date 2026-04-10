# Change Request 007: Job Location Required — Enforce and Add snc job update

**Date:** 2026-04-06

---

## Problem

Jobs can be created without a `locationId`, but every job must have a physical location. Without a location, equipment dispatched to that job has no coordinates and cannot appear on the map. JOB-002, JOB-003, JOB-004 and PROJ-2026-001 were created without locations (location was not required at the time).

## Data Fix Applied (2026-04-06, via Management API)

The existing jobs were patched directly:
- JOB-002 → LOC-002 (Sparks Equipment Yard — Greg Street)
- JOB-003 → LOC-003 (South Reno Staging Yard — Veterans Pkwy)
- JOB-004 → LOC-003 (South Reno Staging Yard — Veterans Pkwy)
- PROJ-2026-001 → YARD-01 (Main Equipment Yard)

## Migration 006: Make locationId NOT NULL on Job

```sql
-- First ensure all jobs have a locationId (data fix already applied above)
ALTER TABLE "Job" ALTER COLUMN "locationId" SET NOT NULL;
```

This prevents any future job from being created without a location.

## CLI Changes

### 1. Make `--location` required on `snc job create`

Currently `--location` is optional. Change it to required. If omitted, return a clear error:
```
Error: --location is required. Every job must have a physical location.
```

### 2. Add `snc job update` command

```
snc job update --id <uuid> [--description <string>] [--location <uuid>] [--code <string>]
```

Allows updating job fields after creation. Required for fixing data without direct DB access.

## Validation

After implementation:
1. `snc job create --business-unit <uuid> --code JOB-TEST --description "Test"` → should fail with location required error
2. `snc job create --business-unit <uuid> --code JOB-TEST --description "Test" --location <uuid>` → should succeed
3. `snc job update --id <uuid> --location <uuid>` → should update the location

## Process Note

The data fix (patching existing jobs) was applied directly via Management API before writing this CR — same pattern as CR-002/003. CR written immediately after to maintain the spec record.
