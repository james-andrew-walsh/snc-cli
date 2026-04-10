-- Migration 007: User Profiles Table + Role Enum
-- Requires: Supabase Auth enabled in project settings (Email/Password provider)
-- Date: 2026-04-07

-- Role enum for all user types in the system
CREATE TYPE user_role AS ENUM (
  'admin',        -- Full CRUD on all tables; James
  'dispatcher',   -- Read all; write DispatchEvent + CrewAssignment; Mo and future SNC staff
  'read_only',    -- SELECT only on all tables
  'agent_write',  -- Read all; write DispatchEvent + Equipment.status + CrewAssignment; Bianca and write agents
  'agent_read'    -- SELECT only; reconciliation and anomaly detection agents
);

-- User profiles table — one row per Supabase Auth user
CREATE TABLE "user_profiles" (
  "id"          UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  "email"       TEXT        NOT NULL,
  "role"        user_role   NOT NULL DEFAULT 'read_only',
  "displayName" TEXT,
  "createdAt"   TIMESTAMPTZ NOT NULL DEFAULT now(),
  "updatedAt"   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Keep updatedAt current on every update
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW."updatedAt" = now();
  RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

CREATE TRIGGER update_user_profiles_updated_at
  BEFORE UPDATE ON "user_profiles"
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add user_profiles to realtime publication (consistent with all other tables)
ALTER PUBLICATION supabase_realtime ADD TABLE "user_profiles";

-- NOTE: After running this migration, manually create the admin user in the
-- Supabase Auth dashboard and insert their profile row:
--
-- INSERT INTO "user_profiles" ("id", "email", "role", "displayName")
-- VALUES ('<auth.users uuid for james>', 'james@amplifyluxury.com', 'admin', 'James Walsh');
