# Change Request AUTH-001: User Profiles Table + Role Enum

**Date:** 2026-04-07
**Status:** Pending — do not implement yet

---

## Problem

The system has no concept of identity. There is one Supabase anon key shared by every client — the CLI, the dashboard, and all agents. No record exists of who performed any action, and there is no mechanism to restrict what any client can do.

Before RLS policies can be written (AUTH-002), Supabase Auth must be enabled and a `user_profiles` table must exist to carry each authenticated user's role.

## What to Build

### Migration 007: Enable Auth + user_profiles

1. Enable Supabase Auth in the Supabase project settings (Email/Password provider at minimum).

2. Create the `user_profiles` table:

```sql
CREATE TYPE user_role AS ENUM (
  'admin',
  'dispatcher',
  'read_only',
  'agent_write',
  'agent_read'
);

CREATE TABLE "user_profiles" (
  "id" UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  "email" TEXT NOT NULL,
  "role" user_role NOT NULL DEFAULT 'read_only',
  "displayName" TEXT,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trigger to keep updatedAt current
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW."updatedAt" = now();
  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_user_profiles_updated_at
  BEFORE UPDATE ON "user_profiles"
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

3. Seed initial admin user (James):
   - Create `james@amplifyluxury.com` in Supabase Auth dashboard
   - Insert matching row into `user_profiles` with role `admin`

### Role Definitions

| Role | Intended User | Capabilities |
|---|---|---|
| `admin` | James | Full CRUD on all tables, schema changes, user management |
| `dispatcher` | Mo (and future SNC staff) | Read all, write DispatchEvent + CrewAssignment |
| `read_only` | Guest / monitoring humans | SELECT only on all tables |
| `agent_write` | Bianca and other write-capable agents | Read all, write DispatchEvent + Equipment.status + CrewAssignment |
| `agent_read` | Reconciliation/anomaly detection agents | SELECT only |

## Files Changed

| Scope | Change |
|---|---|
| Supabase dashboard | Enable Email/Password Auth provider |
| `supabase/migrations/007_user_profiles.sql` | New migration (in snc-cli or snc-dashboard repo) |
| Supabase Auth | Seed James as admin user |

## Validation

1. `user_profiles` table exists with correct columns and role enum
2. Auth provider is enabled — email/password signup works in Supabase dashboard
3. James's user exists in `auth.users` with matching row in `user_profiles` with role `admin`
4. All other tables remain accessible (RLS not enabled yet — that is AUTH-002)

## Notes

- Do not enable RLS in this CR. That is AUTH-002. Enabling RLS before policies exist locks everyone out.
- The `user_profiles` table itself should have RLS enabled when AUTH-002 runs — users can read their own row, admins can read all.
- `user_profiles` should be added to the Supabase realtime publication (consistent with all other tables).
