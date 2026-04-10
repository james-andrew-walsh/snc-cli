-- Migration: 002_add_dispatch_and_employees
-- Description: Adds Employee and DispatchEvent tables to model HCSS Dispatcher intent. Adds status to Equipment.
-- Date: 2026-04-05

-- =============================================
-- Equipment Additions
-- =============================================
ALTER TABLE "Equipment" 
ADD COLUMN IF NOT EXISTS "status" text DEFAULT 'Available';

COMMENT ON COLUMN "Equipment"."status" IS 'Dispatcher visual state (Available, In Use, Down)';

-- =============================================
-- Employee
-- =============================================
CREATE TABLE IF NOT EXISTS "Employee" (
    "id"             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "businessUnitId" uuid NOT NULL REFERENCES "BusinessUnit"("id") ON DELETE CASCADE,
    "firstName"      text NOT NULL,
    "lastName"       text NOT NULL,
    "employeeCode"   text NOT NULL,
    "role"           text NOT NULL DEFAULT 'Crew Member',
    "createdAt"      timestamptz NOT NULL DEFAULT now(),
    "updatedAt"      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "Employee_code_businessUnit_unique" UNIQUE ("businessUnitId", "employeeCode")
);

COMMENT ON TABLE "Employee" IS 'Represents crew leads, members, and dispatch drivers (from HCSS Dispatcher)';

CREATE INDEX IF NOT EXISTS "Employee_businessUnitId_idx" ON "Employee"("businessUnitId");

-- Apply updatedAt trigger
CREATE TRIGGER update_Employee_updatedAt
    BEFORE UPDATE ON "Employee"
    FOR EACH ROW EXECUTE FUNCTION update_updatedAt_column();


-- =============================================
-- DispatchEvent
-- =============================================
CREATE TABLE IF NOT EXISTS "DispatchEvent" (
    "id"             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "equipmentId"    uuid NOT NULL REFERENCES "Equipment"("id") ON DELETE CASCADE,
    "jobId"          uuid REFERENCES "Job"("id") ON DELETE CASCADE,
    "locationId"     uuid REFERENCES "Location"("id") ON DELETE CASCADE,
    "driverId"       uuid REFERENCES "Employee"("id") ON DELETE SET NULL,
    "startDate"      date NOT NULL,
    "endDate"        date,
    "notes"          text,
    "createdAt"      timestamptz NOT NULL DEFAULT now(),
    "updatedAt"      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "DispatchEvent_destination_check" CHECK (
        ("jobId" IS NOT NULL AND "locationId" IS NULL) OR 
        ("jobId" IS NULL AND "locationId" IS NOT NULL)
    )
);

COMMENT ON TABLE "DispatchEvent" IS 'Represents a scheduled move from HCSS Dispatcher (the Intent)';

CREATE INDEX IF NOT EXISTS "DispatchEvent_equipmentId_idx" ON "DispatchEvent"("equipmentId");
CREATE INDEX IF NOT EXISTS "DispatchEvent_jobId_idx" ON "DispatchEvent"("jobId");
CREATE INDEX IF NOT EXISTS "DispatchEvent_locationId_idx" ON "DispatchEvent"("locationId");
CREATE INDEX IF NOT EXISTS "DispatchEvent_startDate_idx" ON "DispatchEvent"("startDate");

-- Apply updatedAt trigger
CREATE TRIGGER update_DispatchEvent_updatedAt
    BEFORE UPDATE ON "DispatchEvent"
    FOR EACH ROW EXECUTE FUNCTION update_updatedAt_column();