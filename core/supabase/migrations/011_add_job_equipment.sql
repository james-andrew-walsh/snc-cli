-- Migration: 011_add_job_equipment
-- Description: Add JobEquipment mirror table and prepare schema for HCSS sync
-- Date: 2026-04-09

-- =============================================
-- 1. Create JobEquipment mirror table
-- =============================================
CREATE TABLE IF NOT EXISTS "JobEquipment" (
    "id"                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "hcssId"               uuid NOT NULL,
    "businessUnitId"       uuid,
    "businessUnitCode"     text,
    "jobHcssId"            uuid NOT NULL,
    "jobCode"              text NOT NULL,
    "equipmentHcssId"      uuid,
    "equipmentCode"        text NOT NULL,
    "equipmentDescription" text,
    "isActive"             boolean NOT NULL DEFAULT true,
    "operatorPayClassId"   uuid,
    "operatorPayClassCode" text,
    "lastSyncedAt"         timestamptz NOT NULL DEFAULT now(),
    "createdAt"            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS "JobEquipment_equipmentCode_idx" ON "JobEquipment"("equipmentCode");
CREATE INDEX IF NOT EXISTS "JobEquipment_jobCode_idx" ON "JobEquipment"("jobCode");
CREATE INDEX IF NOT EXISTS "JobEquipment_jobHcssId_idx" ON "JobEquipment"("jobHcssId");
CREATE INDEX IF NOT EXISTS "JobEquipment_isActive_idx" ON "JobEquipment"("isActive");

-- =============================================
-- 2. Make Job.locationId nullable for HCSS sync
--    (HCSS jobs don't provide locationId; was NOT NULL from migration 006)
-- =============================================
ALTER TABLE "Job" ALTER COLUMN "locationId" DROP NOT NULL;

-- =============================================
-- 3. Drop FK and UNIQUE constraints on mirror tables
--    HCSS uses its own UUIDs for businessUnitId that don't match
--    our auto-generated BusinessUnit PKs. Mirror tables should be
--    constraint-free since HCSS is the source of truth.
-- =============================================
ALTER TABLE "Equipment" DROP CONSTRAINT IF EXISTS "Equipment_businessUnitId_fkey";
ALTER TABLE "Job" DROP CONSTRAINT IF EXISTS "Job_businessUnitId_fkey";
ALTER TABLE "Job" DROP CONSTRAINT IF EXISTS "Job_locationId_fkey";
ALTER TABLE "Location" DROP CONSTRAINT IF EXISTS "Location_businessUnitId_fkey";
ALTER TABLE "Location" DROP CONSTRAINT IF EXISTS "Location_code_businessUnit_unique";
ALTER TABLE "Equipment" DROP CONSTRAINT IF EXISTS "Equipment_code_businessUnit_unique";
ALTER TABLE "Job" DROP CONSTRAINT IF EXISTS "Job_code_businessUnit_unique";
ALTER TABLE "BusinessUnit" DROP CONSTRAINT IF EXISTS "BusinessUnit_code_key";

-- =============================================
-- 4. RPC function: truncate all mirror tables for sync
--    CASCADE handles dependent simulation-era tables
-- =============================================
CREATE OR REPLACE FUNCTION sync_truncate_mirrors()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    TRUNCATE "JobEquipment", "Equipment", "Job", "Location", "BusinessUnit" CASCADE;
END;
$$;
