-- Migration 008: Row-Level Security on All Tables
-- Requires: Migration 007 (user_profiles + user_role enum must exist)
-- Date: 2026-04-07

-- Helper function: returns the role of the currently authenticated user
-- SECURITY DEFINER so it can access user_profiles without bypassing RLS
CREATE OR REPLACE FUNCTION get_user_role()
RETURNS user_role AS $$
  SELECT role FROM "user_profiles" WHERE id = auth.uid();
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- ─────────────────────────────────────────────────────────────────────────────
-- BusinessUnit
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE "BusinessUnit" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "all authenticated users can read business units"
  ON "BusinessUnit" FOR SELECT TO authenticated
  USING (true);

CREATE POLICY "admins can insert business units"
  ON "BusinessUnit" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin');

CREATE POLICY "admins can update business units"
  ON "BusinessUnit" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin');

CREATE POLICY "admins can delete business units"
  ON "BusinessUnit" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin');

-- ─────────────────────────────────────────────────────────────────────────────
-- Equipment
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE "Equipment" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "all authenticated users can read equipment"
  ON "Equipment" FOR SELECT TO authenticated
  USING (true);

CREATE POLICY "admins can insert equipment"
  ON "Equipment" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin');

CREATE POLICY "admins and agents can update equipment"
  ON "Equipment" FOR UPDATE TO authenticated
  USING (get_user_role() IN ('admin', 'agent_write'));

CREATE POLICY "admins can delete equipment"
  ON "Equipment" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin');

-- ─────────────────────────────────────────────────────────────────────────────
-- Job
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE "Job" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "all authenticated users can read jobs"
  ON "Job" FOR SELECT TO authenticated
  USING (true);

CREATE POLICY "admins and dispatchers can insert jobs"
  ON "Job" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() IN ('admin', 'dispatcher'));

CREATE POLICY "admins and dispatchers can update jobs"
  ON "Job" FOR UPDATE TO authenticated
  USING (get_user_role() IN ('admin', 'dispatcher'));

CREATE POLICY "admins can delete jobs"
  ON "Job" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin');

-- ─────────────────────────────────────────────────────────────────────────────
-- Location
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE "Location" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "all authenticated users can read locations"
  ON "Location" FOR SELECT TO authenticated
  USING (true);

CREATE POLICY "admins can insert locations"
  ON "Location" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin');

CREATE POLICY "admins can update locations"
  ON "Location" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin');

CREATE POLICY "admins can delete locations"
  ON "Location" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin');

-- ─────────────────────────────────────────────────────────────────────────────
-- Employee
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE "Employee" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "all authenticated users can read employees"
  ON "Employee" FOR SELECT TO authenticated
  USING (true);

CREATE POLICY "admins can insert employees"
  ON "Employee" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin');

CREATE POLICY "admins can update employees"
  ON "Employee" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin');

CREATE POLICY "admins can delete employees"
  ON "Employee" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin');

-- ─────────────────────────────────────────────────────────────────────────────
-- DispatchEvent
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE "DispatchEvent" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "all authenticated users can read dispatch events"
  ON "DispatchEvent" FOR SELECT TO authenticated
  USING (true);

CREATE POLICY "admins, dispatchers, and agents can insert dispatch events"
  ON "DispatchEvent" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() IN ('admin', 'dispatcher', 'agent_write'));

CREATE POLICY "admins, dispatchers, and agents can update dispatch events"
  ON "DispatchEvent" FOR UPDATE TO authenticated
  USING (get_user_role() IN ('admin', 'dispatcher', 'agent_write'));

CREATE POLICY "admins and dispatchers can delete dispatch events"
  ON "DispatchEvent" FOR DELETE TO authenticated
  USING (get_user_role() IN ('admin', 'dispatcher'));

-- ─────────────────────────────────────────────────────────────────────────────
-- CrewAssignment
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE "CrewAssignment" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "all authenticated users can read crew assignments"
  ON "CrewAssignment" FOR SELECT TO authenticated
  USING (true);

CREATE POLICY "admins, dispatchers, and agents can insert crew assignments"
  ON "CrewAssignment" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() IN ('admin', 'dispatcher', 'agent_write'));

CREATE POLICY "admins, dispatchers, and agents can update crew assignments"
  ON "CrewAssignment" FOR UPDATE TO authenticated
  USING (get_user_role() IN ('admin', 'dispatcher', 'agent_write'));

CREATE POLICY "admins and dispatchers can delete crew assignments"
  ON "CrewAssignment" FOR DELETE TO authenticated
  USING (get_user_role() IN ('admin', 'dispatcher'));

-- ─────────────────────────────────────────────────────────────────────────────
-- user_profiles
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE "user_profiles" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users can read their own profile"
  ON "user_profiles" FOR SELECT TO authenticated
  USING (id = auth.uid() OR get_user_role() = 'admin');

CREATE POLICY "admins can insert user profiles"
  ON "user_profiles" FOR INSERT TO authenticated
  WITH CHECK (get_user_role() = 'admin');

CREATE POLICY "admins can update user profiles"
  ON "user_profiles" FOR UPDATE TO authenticated
  USING (get_user_role() = 'admin');

CREATE POLICY "admins can delete user profiles"
  ON "user_profiles" FOR DELETE TO authenticated
  USING (get_user_role() = 'admin');

-- ─────────────────────────────────────────────────────────────────────────────
-- Transitional public read policy (TEMPORARY)
-- Allows the dashboard to load data before AUTH-003 (dashboard login) ships.
-- Remove this policy once AUTH-003 is deployed.
-- ─────────────────────────────────────────────────────────────────────────────
-- Uncomment the block below only if you need a transitional period where the
-- dashboard works without login. Not recommended — deploy AUTH-003 first.
--
-- CREATE POLICY "temporary public read on all tables for transition period"
--   ON "BusinessUnit" FOR SELECT TO anon USING (true);
-- (repeat for Equipment, Job, Location, Employee, DispatchEvent, CrewAssignment)
