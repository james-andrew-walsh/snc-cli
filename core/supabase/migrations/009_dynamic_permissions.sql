-- Migration 009: Dynamic Operation-Level Permissions
-- Replaces static role-based RLS policies with per-user JSONB permission map
-- Requires: Migration 008 (RLS + user_profiles must exist)
-- Date: 2026-04-07

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 1: Add permissions JSONB column to user_profiles
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE "user_profiles"
ADD COLUMN "permissions" JSONB NOT NULL DEFAULT '{}';

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 2: Create can_perform() helper function
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION can_perform(resource text, operation text)
RETURNS boolean AS $$
  SELECT COALESCE(
    (SELECT (permissions->resource) ? operation
     FROM "user_profiles" WHERE id = auth.uid()),
    false
  );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 3: Drop existing static operation policies, replace with can_perform()
-- Note: SELECT policies are unchanged — all authenticated users can read
-- Note: get_user_role() = 'admin' override ensures admin is never locked out
-- ─────────────────────────────────────────────────────────────────────────────

-- BusinessUnit
DROP POLICY IF EXISTS "admins can insert business units" ON "BusinessUnit";
DROP POLICY IF EXISTS "admins can update business units" ON "BusinessUnit";
DROP POLICY IF EXISTS "admins can delete business units" ON "BusinessUnit";

CREATE POLICY "can create business unit" ON "BusinessUnit" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin' OR can_perform('business-unit', 'create'));
CREATE POLICY "can update business unit" ON "BusinessUnit" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('business-unit', 'update'));
CREATE POLICY "can delete business unit" ON "BusinessUnit" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('business-unit', 'delete'));

-- Equipment
DROP POLICY IF EXISTS "admins can insert equipment" ON "Equipment";
DROP POLICY IF EXISTS "admins and agents can update equipment" ON "Equipment";
DROP POLICY IF EXISTS "admins can delete equipment" ON "Equipment";

CREATE POLICY "can create equipment" ON "Equipment" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin' OR can_perform('equipment', 'create'));
CREATE POLICY "can update equipment" ON "Equipment" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('equipment', 'update'));
CREATE POLICY "can delete equipment" ON "Equipment" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('equipment', 'delete'));

-- Job
DROP POLICY IF EXISTS "admins and dispatchers can insert jobs" ON "Job";
DROP POLICY IF EXISTS "admins and dispatchers can update jobs" ON "Job";
DROP POLICY IF EXISTS "admins can delete jobs" ON "Job";

CREATE POLICY "can create job" ON "Job" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin' OR can_perform('job', 'create'));
CREATE POLICY "can update job" ON "Job" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('job', 'update'));
CREATE POLICY "can delete job" ON "Job" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('job', 'delete'));

-- Location
DROP POLICY IF EXISTS "admins can insert locations" ON "Location";
DROP POLICY IF EXISTS "admins can update locations" ON "Location";
DROP POLICY IF EXISTS "admins can delete locations" ON "Location";

CREATE POLICY "can create location" ON "Location" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin' OR can_perform('location', 'create'));
CREATE POLICY "can update location" ON "Location" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('location', 'update'));
CREATE POLICY "can delete location" ON "Location" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('location', 'delete'));

-- Employee
DROP POLICY IF EXISTS "admins can insert employees" ON "Employee";
DROP POLICY IF EXISTS "admins can update employees" ON "Employee";
DROP POLICY IF EXISTS "admins can delete employees" ON "Employee";

CREATE POLICY "can create employee" ON "Employee" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin' OR can_perform('employee', 'create'));
CREATE POLICY "can update employee" ON "Employee" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('employee', 'update'));
CREATE POLICY "can delete employee" ON "Employee" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('employee', 'delete'));

-- DispatchEvent
DROP POLICY IF EXISTS "admins dispatchers and agents can insert dispatch events" ON "DispatchEvent";
DROP POLICY IF EXISTS "admins dispatchers and agents can update dispatch events" ON "DispatchEvent";
DROP POLICY IF EXISTS "admins and dispatchers can delete dispatch events" ON "DispatchEvent";

CREATE POLICY "can schedule dispatch" ON "DispatchEvent" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin' OR can_perform('dispatch', 'schedule'));
CREATE POLICY "can update dispatch" ON "DispatchEvent" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('dispatch', 'schedule'));
CREATE POLICY "can cancel dispatch" ON "DispatchEvent" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('dispatch', 'cancel'));

-- CrewAssignment
DROP POLICY IF EXISTS "admins dispatchers and agents can insert crew assignments" ON "CrewAssignment";
DROP POLICY IF EXISTS "admins dispatchers and agents can update crew assignments" ON "CrewAssignment";
DROP POLICY IF EXISTS "admins and dispatchers can delete crew assignments" ON "CrewAssignment";

CREATE POLICY "can assign crew" ON "CrewAssignment" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin' OR can_perform('crew-assignment', 'assign'));
CREATE POLICY "can update crew assignment" ON "CrewAssignment" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('crew-assignment', 'assign'));
CREATE POLICY "can remove crew" ON "CrewAssignment" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin' OR can_perform('crew-assignment', 'remove'));

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 4: Seed default permissions for existing users
-- ─────────────────────────────────────────────────────────────────────────────

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
