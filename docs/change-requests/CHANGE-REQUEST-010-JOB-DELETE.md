# Change Request 010: Add snc job delete Command

**Date:** 2026-04-06

---

## Background

There is no way to delete a job via the CLI. The original seeded job `PROJ-2026-001` (Highland Residence - Foundation Excavation) is test data that should be removed. Additionally, jobs that are completed or cancelled will need to be removed from the system over time.

Deleting a job requires handling FK-dependent records first:
- `DispatchEvent` records referencing the job's `jobId`
- `CrewAssignment` records referencing the job's `jobId`

These must be deleted (or the command must refuse and report what depends on the job) before the job itself can be deleted.

## The Command

```
snc job delete --id <uuid> [--force]
```

**Default behavior (no --force):**
- Check for dependent DispatchEvents and CrewAssignments
- If any exist, print them and exit with an error:
  ```
  Error: Cannot delete job — 2 dispatch event(s) and 1 crew assignment(s) reference this job.
  Use --force to cancel all dependent records and delete the job.
  ```

**With --force:**
- Delete all DispatchEvents where jobId = the given UUID
- Delete all CrewAssignments where jobId = the given UUID
- Delete the Job record
- Return confirmation JSON

## Instructions for Claude Code

1. Read `EQUIPMENT-TRACKING-PROJECT.md` for context
2. Add `delete` command to `snc_cli/commands/job.py`
3. Follow the same pattern as `snc dispatch cancel` for the deletion call
4. Implement dependency check (query DispatchEvent and CrewAssignment by jobId, count results)
5. If count > 0 and no --force, print error and exit
6. If --force, delete dependents first then delete job

Environment vars for testing:
```
export SUPABASE_URL=https://ghscnwwatguzmeuabspd.supabase.co
export SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdoc2Nud3dhdGd1em1ldWFic3BkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyMjc3NjAsImV4cCI6MjA5MDgwMzc2MH0.l50Xlpw5q_HgvbbEg-0mLtx-YkRhV8tDRjecJ6PDnmM
```

CLI binary: `/tmp/snc-cli/.venv/bin/snc`

## Test

PROJ-2026-001 id: `30ad6505-568b-4876-aa80-346e41a2a953`

1. First try without --force — should show dependency error
2. Then with --force — should delete dependents and the job
3. Verify with `snc job list` — PROJ-2026-001 should be gone

## Commit and push

```
git add -A
git commit -m "feat: CR-010 — snc job delete command with --force flag"
git push
```

## Validation

After implementation, `snc job list` should return 5 jobs (PROJ-2026-001 removed).
