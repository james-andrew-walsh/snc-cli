-- Migration 006: Make Job.locationId NOT NULL
-- Every job must have a physical location. Without one, equipment dispatched
-- to that job has no coordinates and cannot appear on the map.
-- Data fix (all existing jobs assigned locations) applied 2026-04-06 before this migration.

ALTER TABLE "Job" ALTER COLUMN "locationId" SET NOT NULL;
