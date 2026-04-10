# Change Request AUTH-002: Row-Level Security on All Tables

**Date:** 2026-04-07
**Status:** Pending — do not implement yet
**Depends on:** AUTH-001 (user_profiles table + role enum must exist)

---

## Problem

All 7 operational tables (BusinessUnit, Equipment, Job, Location, Employee, DispatchEvent, CrewAssignment) are currently unprotected. Any client with the anon key can read and write anything. Once AUTH-001 establishes user identity and roles, RLS policies can enforce what each role is actually permitted to do.

## What to Build

### Migration 008: Enable RLS + Write Policies

For each table, the pattern is:
1. `ALTER TABLE "<TableName>" ENABLE ROW LEVEL SECURITY;`
2. A SELECT policy (who can read)
3. An INSERT policy (who can write)
4. An UPDATE policy (who can modify)
5. A DELETE policy (who can delete)

All policies use a helper function to look up the caller's role:

```sql
CREATE OR REPLACE FUNCTION get_user_role()
RETURNS user_role AS $$
  SELECT role FROM "user_profiles" WHERE id = auth.uid();
$$ LANGUAGE sql STABLE SECURITY DEFINER;
```

### Policy Matrix

| Table | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| BusinessUnit | all roles | admin | admin | admin |
| Equipment | all roles | admin | admin, agent_write | admin |
| Job | all roles | admin, dispatcher | admin, dispatcher | admin |
| Location | all roles | admin | admin | admin |
| Employee | all roles | admin | admin | admin |
| DispatchEvent | all roles | admin, dispatcher, agent_write | admin, dispatcher, agent_write | admin, dispatcher |
| CrewAssignment | all roles | admin, dispatcher, agent_write | admin, dispatcher, agent_write | admin, dispatcher |
| user_profiles | own row + admin | admin (via trigger) | admin | admin |

### Example Policy (DispatchEvent INSERT)

```sql
CREATE POLICY "dispatcher and agents can create dispatch events"
  ON "DispatchEvent"
  FOR INSERT
  TO authenticated
  WITH CHECK (
    get_user_role() IN ('admin', 'dispatcher', 'agent_write')
  );
```

### Service Role Exception

The Supabase `service_role` key bypasses RLS by design. This key must NEVER be used by CLI, dashboard, or agents — it is for migrations and admin scripts only. All application clients use user JWTs (after AUTH-003/004) or the anon key with RLS enforced.

## Files Changed

| Scope | Change |
|---|---|
| `supabase/migrations/008_row_level_security.sql` | New migration enabling RLS and writing all policies |

## Validation

1. As `admin` user: can INSERT into BusinessUnit, Equipment, Job, Location, Employee
2. As `dispatcher` user: can INSERT into DispatchEvent and CrewAssignment, cannot INSERT into Equipment
3. As `read_only` user: can SELECT from all tables, INSERT on any table returns 403
4. As `agent_write` user: can INSERT into DispatchEvent, cannot INSERT into BusinessUnit
5. As `agent_read` user: can SELECT all tables, cannot INSERT anywhere
6. Unauthenticated request (anon key, no JWT): SELECT blocked on all tables (or returns empty — depending on whether a public read policy is desired)

## Notes

- Decision needed before implementing: should unauthenticated (anon) clients be able to SELECT? Currently the dashboard loads before the user logs in. Two options: (a) add a public SELECT policy for all tables so the dashboard works before auth is implemented (transitional), or (b) require login before the dashboard shows any data. Option (a) is safer during the transition period — remove it when AUTH-005 (dashboard login) ships.
- The `user_profiles` policy must allow users to read their own row so the CLI can call `snc whoami`.
