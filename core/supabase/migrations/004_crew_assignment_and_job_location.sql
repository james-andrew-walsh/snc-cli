-- Migration 004: Crew Assignment, Job-Location Relationship, and Dispatch Refinement
-- Date: 2026-04-06
--
-- Changes:
-- 1. Add locationId FK to Job (a job happens at a physical location)
-- 2. Create CrewAssignment table (employees assigned to jobs)
-- 3. Rename DispatchEvent.driverId to operatorId (the crew member responsible for the machine on site)

-- 1. Add locationId to Job
ALTER TABLE "Job" ADD COLUMN "locationId" UUID REFERENCES "Location"(id);

-- 2. Create CrewAssignment table
CREATE TABLE "CrewAssignment" (
  "id"          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "jobId"       UUID NOT NULL REFERENCES "Job"(id),
  "employeeId"  UUID NOT NULL REFERENCES "Employee"(id),
  "role"        TEXT,
  "startDate"   DATE NOT NULL,
  "endDate"     DATE,
  "notes"       TEXT,
  "createdAt"   TIMESTAMPTZ DEFAULT now(),
  "updatedAt"   TIMESTAMPTZ DEFAULT now()
);

-- 3. Rename driverId to operatorId on DispatchEvent
ALTER TABLE "DispatchEvent" RENAME COLUMN "driverId" TO "operatorId";
