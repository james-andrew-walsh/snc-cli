-- Migration: 010_add_hcss_fields
-- Description: Expand schema to match HCSS API fields
-- Date: 2026-04-08

-- =============================================
-- Add HCSS ID columns for sync tracking
-- =============================================

ALTER TABLE "BusinessUnit" ADD COLUMN IF NOT EXISTS "hcssId" uuid;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "hcssId" uuid;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "hcssId" uuid;
ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "hcssId" uuid;

-- Unique constraints for upsert by hcssId
CREATE UNIQUE INDEX IF NOT EXISTS "BusinessUnit_hcssId_idx" ON "BusinessUnit"("hcssId") WHERE "hcssId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "Equipment_hcssId_idx" ON "Equipment"("hcssId") WHERE "hcssId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "Job_hcssId_idx" ON "Job"("hcssId") WHERE "hcssId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "Location_hcssId_idx" ON "Location"("hcssId") WHERE "hcssId" IS NOT NULL;

-- =============================================
-- Add sync tracking timestamps
-- =============================================

ALTER TABLE "BusinessUnit" ADD COLUMN IF NOT EXISTS "lastSyncedAt" timestamptz;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "lastSyncedAt" timestamptz;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "lastSyncedAt" timestamptz;
ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "lastSyncedAt" timestamptz;

-- =============================================
-- Expand Equipment table to match E360 ApiEquipmentRead
-- =============================================

ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "equipmentType" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "accountingCode" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "vin" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "weight" double precision;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "length" double precision;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "width" double precision;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "height" double precision;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "numberAxles" integer;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "tireSize" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "status" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "enabled" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "ratedPowerHP" integer;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "ratedPowerKW" integer;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "defaultFuel" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "purchaseDate" timestamptz;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "purchasePrice" double precision;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "jobCode" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "locationName" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "onLoanBusinessUnitId" uuid;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "imageUrl" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "region" text;
ALTER TABLE "Equipment" ADD COLUMN IF NOT EXISTS "division" text;

COMMENT ON COLUMN "Equipment"."status" IS 'E360 status: AVAIL, STANDBY, IN SERVICE, DOWN, etc.';
COMMENT ON COLUMN "Equipment"."enabled" IS 'Y/N flag from E360';
COMMENT ON COLUMN "Equipment"."jobCode" IS 'Current job assignment from E360';
COMMENT ON COLUMN "Equipment"."locationName" IS 'Current location from E360';

-- =============================================
-- Expand Job table to match HeavyJob ApiJobRead
-- =============================================

ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "legacyId" text;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "payItemSetupType" text;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "startofpayweek" text;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "relatedEstimateCodes" text[] DEFAULT '{}';
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "jobNote" text;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "isDeleted" boolean DEFAULT false;

-- Address object fields from HCSS
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "address" jsonb;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "latitude" double precision;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "longitude" double precision;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "regionCode" text;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "divisionCode" text;

COMMENT ON COLUMN "Job"."status" IS 'HeavyJob status: active, completed, discontinued, inactive';
COMMENT ON COLUMN "Job"."latitude" IS 'Derived from geocoding address or telematics';
COMMENT ON COLUMN "Job"."longitude" IS 'Derived from geocoding address or telematics';

-- =============================================
-- Expand Location table to match E360 ApiLocationRead
-- =============================================

ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "altCode" text;
ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "enabled" text;
ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "address" jsonb;
ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "latitude" double precision;
ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "longitude" double precision;
ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "regionCode" text;
ALTER TABLE "Location" ADD COLUMN IF NOT EXISTS "divisionCode" text;

COMMENT ON COLUMN "Location"."enabled" IS 'Y/N flag from E360';
COMMENT ON COLUMN "Location"."latitude" IS 'Derived from geocoding address';
COMMENT ON COLUMN "Location"."longitude" IS 'Derived from geocoding address';

-- =============================================
-- Expand BusinessUnit table
-- =============================================

ALTER TABLE "BusinessUnit" ADD COLUMN IF NOT EXISTS "hcssSource" text;
ALTER TABLE "BusinessUnit" ADD COLUMN IF NOT EXISTS "credentialsId" uuid;

-- =============================================
-- Add indexes for common query patterns
-- =============================================

CREATE INDEX IF NOT EXISTS "Equipment_status_idx" ON "Equipment"("status");
CREATE INDEX IF NOT EXISTS "Equipment_jobCode_idx" ON "Equipment"("jobCode");
CREATE INDEX IF NOT EXISTS "Equipment_locationName_idx" ON "Equipment"("locationName");
CREATE INDEX IF NOT EXISTS "Job_status_idx" ON "Job"("status");
CREATE INDEX IF NOT EXISTS "Location_enabled_idx" ON "Location"("enabled");
