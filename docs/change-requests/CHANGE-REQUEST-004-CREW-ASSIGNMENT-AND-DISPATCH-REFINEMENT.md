# Change Request 004: Crew Assignment, Job-Location Relationship, and Dashboard Display Fixes

**Date:** 2026-04-06
**Priority:** High — foundational to dispatch workflow

---

## Background & Problem Statement

The current data model has two structural gaps that prevent the dispatch workflow from being coherent:

1. **Jobs have no physical location.** A `Job` is just a code and description floating in space. In reality, a job site *is* a place. The `Location` table already models physical places (yards, staging areas, job sites). Jobs need to reference a Location.

2. **No crew assignment model.** The current `DispatchEvent` has a `driverId` field, but this models only the person *moving* a machine — not the person *responsible for it on site*. In SNC's real workflow:
   - Employees are first **assigned to a Job** (crew assignment)
   - Equipment is then **dispatched to a Job**, with the responsible operator being a crew member already assigned there
   - Equipment always has a human responsible for it

Without crew assignment, we cannot answer: "Who is working on Job X?" or "Who is responsible for this machine at this site?"

---

## The Correct Mental Model

```
Location  ←──  Job  ←──  CrewAssignment (Employee assigned to Job)
                │
                └──  DispatchEvent (Equipment dispatched to Job, operated by assigned crew member)
```

- **Location:** A physical place (yard, staging area, job site address)
- **Job:** A construction project at a Location
- **CrewAssignment:** An Employee assigned to a Job for a date range
- **DispatchEvent:** Equipment dispatched to a Job destination, with `operatorId` pointing to the crew member responsible for that machine (should be a member with an active CrewAssignment at that Job)

---

## Changes Required

### 1. Database Migration: `004_crew_assignment_and_job_location.sql`

**A. Add `locationId` to `Job` table**
```sql
ALTER TABLE "Job" ADD COLUMN "locationId" UUID REFERENCES "Location"(id);
```

**B. Create `CrewAssignment` table**
```sql
CREATE TABLE "CrewAssignment" (
  "id"             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "jobId"          UUID NOT NULL REFERENCES "Job"(id),
  "employeeId"     UUID NOT NULL REFERENCES "Employee"(id),
  "role"           TEXT,           -- their role on this specific job (e.g. Operator, Crew Lead)
  "startDate"      DATE NOT NULL,
  "endDate"        DATE,           -- null = ongoing
  "notes"          TEXT,
  "createdAt"      TIMESTAMPTZ DEFAULT now(),
  "updatedAt"      TIMESTAMPTZ DEFAULT now()
);
```

**C. Rename `driverId` to `operatorId` on `DispatchEvent`**

The `driverId` field was named for the person *driving the truck to deliver* the equipment. The correct concept is the *operator* — the crew member responsible for the machine at the job site. Renaming makes the model accurate.

```sql
ALTER TABLE "DispatchEvent" RENAME COLUMN "driverId" TO "operatorId";
```

---

### 2. CLI Changes: `snc crew-assignment` commands

New command group `snc crew-assignment`:

- `snc crew-assignment list [--job <uuid>] [--employee <uuid>]`
  - Returns all crew assignments, optionally filtered by job or employee
- `snc crew-assignment get --id <uuid>`
- `snc crew-assignment assign --job <uuid> --employee <uuid> --start <YYYY-MM-DD> [--end <YYYY-MM-DD>] [--role <string>] [--notes <string>]`
  - Assigns an employee to a job
- `snc crew-assignment remove --id <uuid>`
  - Ends/removes a crew assignment

Update `snc job create` and `snc job get` to accept/display `--location <uuid>`.

Update `snc dispatch schedule` to use `--operator <uuid>` instead of `--driver <uuid>`.

---

### 3. Dashboard Changes (Frontend Only — No Migration)

**A. Dispatch Schedule View: Resolve UUIDs to human-readable names**

Currently shows raw UUIDs for Equipment, Job, and Operator. Should show:
- Equipment: `{make} {model} ({code})` e.g. "Caterpillar 320 (CAT-320-01)"
- Job: `{code} — {description}` e.g. "JOB-002 — Sparks Industrial Park"
- Location (if set): `{code} — {description}`
- Operator: `{firstName} {lastName}` e.g. "Mike Torres"

Implementation: Fetch lookup tables (Equipment, Job, Location, Employee) alongside DispatchEvent and resolve IDs client-side before rendering.

**B. Equipment View: Add "Assigned To" column**

Show where each piece of equipment is currently assigned, based on active DispatchEvent (where today falls between `startDate` and `endDate`).

- If active dispatch exists: show Job code or Location code
- If no active dispatch: show "—" or leave blank

Implementation: Fetch DispatchEvent data alongside Equipment, join client-side.

**C. Jobs & Locations View: Show Location on Job rows**

Add a "Location" column to the Jobs table that resolves `locationId` to the Location's code/description.

---

## Workflow After This Change

1. Create a Location (job site address): `snc location create ...`
2. Create a Job at that Location: `snc job create --location <uuid> ...`
3. Assign crew to the Job: `snc crew-assignment assign --job <uuid> --employee <uuid> --start 2026-04-07`
4. Dispatch equipment to the Job with an operator: `snc dispatch schedule --equipment <uuid> --job <uuid> --operator <uuid> --start 2026-04-07`
5. Dashboard shows: equipment assigned to job, crew on job, dispatch schedule with human-readable names

---

## Validation

After implementation, the following scenario must work end-to-end:

1. Create a job with a location
2. Assign two employees to that job via `snc crew-assignment assign`
3. Dispatch two pieces of equipment to that job with operators
4. Dashboard Equipment view shows both machines as "Assigned To: JOB-002"
5. Dashboard Dispatch Schedule shows machine names, job names, and operator names — no raw UUIDs
6. Dashboard Jobs & Locations shows the Location for each Job

---

## Files to Update

| File | Change |
|---|---|
| `core/supabase/migrations/004_crew_assignment_and_job_location.sql` | New migration (see above) |
| `snc-cli` repo — `snc_cli/commands/` | Add `crew_assignment.py`, update `job.py`, update `dispatch.py` |
| `snc-cli` repo — `snc_cli/main.py` | Register new `crew-assignment` command group |
| `snc-dashboard` repo — `src/views/DispatchSchedule.tsx` | Resolve UUIDs to names |
| `snc-dashboard` repo — `src/views/Equipment.tsx` | Add "Assigned To" column |
| `snc-dashboard` repo — `src/views/JobsLocations.tsx` | Show Location on Job rows |
| `snc-dashboard` repo — `src/lib/types.ts` | Add `CrewAssignment` type, update `DispatchEvent` (driverId → operatorId), add `locationId` to `Job` |

## Instructions for Claude Code

1. Read `EQUIPMENT-TRACKING-PROJECT.md` for full project context
2. Read `CORE-ARCHITECTURE.md` and `CORE-CLI-PRD.md` for design principles
3. Apply migration `004_crew_assignment_and_job_location.sql` via Supabase Management API (see memory/2026-04-05.md for the curl pattern with `User-Agent: curl/8.1.2` header required)
4. Implement CLI changes in `/tmp/snc-cli/`
5. Implement dashboard changes in `/tmp/snc-dashboard/`
6. Commit and push both repos
