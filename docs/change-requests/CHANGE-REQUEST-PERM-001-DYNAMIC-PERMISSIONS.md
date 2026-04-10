# Change Request PERM-001: Dynamic Operation-Level Permissions

**Date:** 2026-04-07
**Status:** Pending — do not implement yet
**Depends on:** AUTH-001 through AUTH-006 (complete)

---

## Problem

The current permission system uses a static `user_role` enum with hardcoded RLS policies. This means:
- Every user with the same role has identical permissions — no per-user customization
- Adding a new permission requires a database migration
- There is no way to say "Mo can schedule dispatches but not cancel them"

We need operation-level permissions stored per user, managed through an admin UI, and enforced dynamically at the database layer.

---

## What to Build

### Migration 009: Dynamic Permissions

**Step 1: Add `permissions` JSONB column to `user_profiles`**

```sql
ALTER TABLE "user_profiles"
ADD COLUMN "permissions" JSONB NOT NULL DEFAULT '{}';
```

The JSONB structure stores allowed operations per resource:

```json
{
  "business-unit": ["list", "get"],
  "equipment": ["list", "get", "update"],
  "dispatch": ["list", "get", "schedule", "cancel"],
  "job": ["list", "get", "create", "update"],
  "location": ["list", "get"],
  "employee": ["list", "get"],
  "crew-assignment": ["list", "get", "assign", "remove"],
  "telemetry": []
}
```

**Step 2: Create `can_perform()` helper function**

```sql
CREATE OR REPLACE FUNCTION can_perform(resource text, operation text)
RETURNS boolean AS $$
  SELECT COALESCE(
    (SELECT (permissions->resource) ? operation
     FROM "user_profiles" WHERE id = auth.uid()),
    false
  );
$$ LANGUAGE sql STABLE SECURITY DEFINER;
```

**Step 3: Replace static RLS policies with dynamic ones**

Drop all existing operation-specific policies and replace with `can_perform()` calls. Keep the static admin override (`get_user_role() = 'admin'`) so the admin is never locked out.

For each table, the new INSERT/UPDATE/DELETE policies follow this pattern:

```sql
-- Example: DispatchEvent INSERT
DROP POLICY "admins dispatchers and agents can insert dispatch events" ON "DispatchEvent";

CREATE POLICY "can schedule dispatch"
  ON "DispatchEvent" FOR INSERT TO authenticated
  WITH CHECK (
    get_user_role() = 'admin' OR can_perform('dispatch', 'schedule')
  );

CREATE POLICY "can update dispatch"
  ON "DispatchEvent" FOR UPDATE TO authenticated
  USING (
    get_user_role() = 'admin' OR can_perform('dispatch', 'schedule')
  );

CREATE POLICY "can cancel dispatch"
  ON "DispatchEvent" FOR DELETE TO authenticated
  USING (
    get_user_role() = 'admin' OR can_perform('dispatch', 'cancel')
  );
```

SELECT policies remain unchanged — all authenticated users can read everything.

**Full policy replacement map:**

| Table | Operation | can_perform key |
|---|---|---|
| BusinessUnit | INSERT | business-unit, create |
| BusinessUnit | UPDATE | business-unit, update (add to schema) |
| BusinessUnit | DELETE | business-unit, delete (add to schema) |
| Equipment | INSERT | equipment, create |
| Equipment | UPDATE | equipment, update |
| Equipment | DELETE | equipment, delete |
| Job | INSERT | job, create |
| Job | UPDATE | job, update |
| Job | DELETE | job, delete |
| Location | INSERT | location, create |
| Location | UPDATE | location, update |
| Location | DELETE | location, delete |
| Employee | INSERT | employee, create |
| Employee | UPDATE | employee, update |
| Employee | DELETE | employee, delete |
| DispatchEvent | INSERT | dispatch, schedule |
| DispatchEvent | UPDATE | dispatch, schedule |
| DispatchEvent | DELETE | dispatch, cancel |
| CrewAssignment | INSERT | crew-assignment, assign |
| CrewAssignment | UPDATE | crew-assignment, assign |
| CrewAssignment | DELETE | crew-assignment, remove |

**Step 4: Seed default permissions for existing users**

```sql
-- admin: full permissions (redundant since get_user_role() = 'admin' bypasses, but good for UI display)
UPDATE "user_profiles" SET "permissions" = '{
  "business-unit": ["list", "get", "create", "update", "delete"],
  "equipment": ["list", "get", "create", "update", "transfer", "delete"],
  "dispatch": ["list", "get", "schedule", "cancel"],
  "job": ["list", "get", "create", "update", "delete"],
  "location": ["list", "get", "create", "update", "delete"],
  "employee": ["list", "get", "create", "update", "delete"],
  "crew-assignment": ["list", "get", "assign", "remove"],
  "telemetry": ["update"]
}'::jsonb
WHERE email = 'james@amplifyluxury.com';

-- agent_write: dispatch + crew + equipment status
UPDATE "user_profiles" SET "permissions" = '{
  "business-unit": ["list", "get"],
  "equipment": ["list", "get", "update"],
  "dispatch": ["list", "get", "schedule"],
  "job": ["list", "get"],
  "location": ["list", "get"],
  "employee": ["list", "get"],
  "crew-assignment": ["list", "get", "assign", "remove"],
  "telemetry": ["update"]
}'::jsonb
WHERE email = 'agent-write@snc.app';

-- agent_read: read only
UPDATE "user_profiles" SET "permissions" = '{
  "business-unit": ["list", "get"],
  "equipment": ["list", "get"],
  "dispatch": ["list", "get"],
  "job": ["list", "get"],
  "location": ["list", "get"],
  "employee": ["list", "get"],
  "crew-assignment": ["list", "get"],
  "telemetry": []
}'::jsonb
WHERE email = 'agent-read@snc.app';
```

**Step 5: Add `permissions` to the `user_profiles` RLS SELECT policy**

The permissions column is part of the user_profiles row — existing SELECT policy already covers it.

---

## Files Changed

| Scope | Change |
|---|---|
| `supabase/migrations/009_dynamic_permissions.sql` | New migration (already written above) |

---

## Validation

1. Log in as `agent-read@snc.app`
2. `snc equipment list` → 5 records returned ✅
3. `snc dispatch schedule ...` → clean error message (not stack trace) — see PERM-003 for error handling
4. Log in as `agent-write@snc.app`
5. `snc dispatch schedule ...` → succeeds ✅
6. `snc equipment create ...` → blocked (agent_write has no create permission on equipment) ✅
7. Query `user_profiles` → all three users have populated `permissions` columns ✅
8. Verify policies in `pg_policies` — old static role policies are gone, new `can_perform` policies exist

## Notes

- The `get_user_role() = 'admin'` override on all policies means the admin is never locked out, even if their permissions JSONB is empty. This is intentional.
- The `user_role` enum is NOT removed. Roles still serve as default templates and display labels. They are just no longer the enforcement mechanism.
- The `dispatcher` role has no user seeded yet — Mo's account will be created via the admin dashboard (PERM-002) with appropriate permissions at that time.
