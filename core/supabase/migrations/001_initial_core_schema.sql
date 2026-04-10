-- Migration: 001_initial_core_schema
-- Description: Core Phase 1 tables for SNC Equipment Tracking MVP
-- Date: 2026-04-04

-- gen_random_uuid() is built into PostgreSQL 17 — no extension neededCREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA public;

-- =============================================
-- BusinessUnit
-- =============================================
CREATE TABLE IF NOT EXISTS "BusinessUnit" (
    "id"          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "code"        text NOT NULL UNIQUE,
    "description" text,
    "createdAt"   timestamptz NOT NULL DEFAULT now(),
    "updatedAt"   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE "BusinessUnit" IS 'Business unit / company entity (mirrors HCSS ApiBusinessUnitRead)';

-- =============================================
-- Equipment
-- =============================================
CREATE TABLE IF NOT EXISTS "Equipment" (
    "id"             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "businessUnitId" uuid NOT NULL REFERENCES "BusinessUnit"("id") ON DELETE CASCADE,
    "code"           text NOT NULL,
    "description"    text,
    "make"           text,
    "model"          text,
    "year"           integer,
    "serialNumber"   text,
    "gpsDeviceTag"   text,
    "hourMeter"      integer DEFAULT 0,
    "odometer"       integer DEFAULT 0,
    "isRental"       boolean DEFAULT false,
    "isActive"       boolean DEFAULT true,
    "createdAt"      timestamptz NOT NULL DEFAULT now(),
    "updatedAt"      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "Equipment_code_businessUnit_unique" UNIQUE ("businessUnitId", "code")
);

COMMENT ON TABLE "Equipment" IS 'Equipment asset (hybrid model: Equipment360 physical + HeavyJob operational)';
COMMENT ON COLUMN "Equipment"."gpsDeviceTag" IS 'GPS device tag for telematics mapping (from HeavyJob)';
COMMENT ON COLUMN "Equipment"."hourMeter" IS 'Most recent hour reading (from Equipment360)';
COMMENT ON COLUMN "Equipment"."odometer" IS 'Most recent odometer reading (from Equipment360)';

-- Index for business unit lookups
CREATE INDEX IF NOT EXISTS "Equipment_businessUnitId_idx" ON "Equipment"("businessUnitId");

-- =============================================
-- Job
-- =============================================
CREATE TABLE IF NOT EXISTS "Job" (
    "id"             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "businessUnitId" uuid NOT NULL REFERENCES "BusinessUnit"("id") ON DELETE CASCADE,
    "code"           text NOT NULL,
    "description"    text,
    "createdAt"      timestamptz NOT NULL DEFAULT now(),
    "updatedAt"      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "Job_code_businessUnit_unique" UNIQUE ("businessUnitId", "code")
);

COMMENT ON TABLE "Job" IS 'Construction job / project (mirrors HCSS ApiJobRead)';

CREATE INDEX IF NOT EXISTS "Job_businessUnitId_idx" ON "Job"("businessUnitId");

-- =============================================
-- Location
-- =============================================
CREATE TABLE IF NOT EXISTS "Location" (
    "id"             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "businessUnitId" uuid NOT NULL REFERENCES "BusinessUnit"("id") ON DELETE CASCADE,
    "code"           text NOT NULL,
    "description"    text,
    "createdAt"      timestamptz NOT NULL DEFAULT now(),
    "updatedAt"      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "Location_code_businessUnit_unique" UNIQUE ("businessUnitId", "code")
);

COMMENT ON TABLE "Location" IS 'Jobsite location (mirrors HCSS ApiLocationRead)';

CREATE INDEX IF NOT EXISTS "Location_businessUnitId_idx" ON "Location"("businessUnitId");

-- =============================================
-- UpdatedAt trigger function
-- =============================================
CREATE OR REPLACE FUNCTION update_updatedAt_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW."updatedAt" = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updatedAt triggers
CREATE TRIGGER update_BusinessUnit_updatedAt
    BEFORE UPDATE ON "BusinessUnit"
    FOR EACH ROW EXECUTE FUNCTION update_updatedAt_column();

CREATE TRIGGER update_Equipment_updatedAt
    BEFORE UPDATE ON "Equipment"
    FOR EACH ROW EXECUTE FUNCTION update_updatedAt_column();

CREATE TRIGGER update_Job_updatedAt
    BEFORE UPDATE ON "Job"
    FOR EACH ROW EXECUTE FUNCTION update_updatedAt_column();

CREATE TRIGGER update_Location_updatedAt
    BEFORE UPDATE ON "Location"
    FOR EACH ROW EXECUTE FUNCTION update_updatedAt_column();
