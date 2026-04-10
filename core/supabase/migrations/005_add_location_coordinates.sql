-- Migration 005: Add lat/lng and geofence to Location table
-- Required for Mapbox map view (CR-006)

ALTER TABLE "Location" 
  ADD COLUMN "latitude" DOUBLE PRECISION,
  ADD COLUMN "longitude" DOUBLE PRECISION,
  ADD COLUMN "geofence" JSONB;

-- Seed realistic coordinates for existing locations
-- YARD-01: Main Equipment Yard (Reno industrial area near I-80)
UPDATE "Location" SET
  "latitude" = 39.5296,
  "longitude" = -119.8138,
  "geofence" = '[[-119.8158, 39.5286], [-119.8118, 39.5286], [-119.8118, 39.5306], [-119.8158, 39.5306], [-119.8158, 39.5286]]'::jsonb
WHERE "code" = 'YARD-01';

-- LOC-002: Sparks Equipment Yard — Greg Street
UPDATE "Location" SET
  "latitude" = 39.5349,
  "longitude" = -119.7527,
  "geofence" = '[[-119.7547, 39.5339], [-119.7507, 39.5339], [-119.7507, 39.5359], [-119.7547, 39.5359], [-119.7547, 39.5339]]'::jsonb
WHERE "code" = 'LOC-002';

-- LOC-003: South Reno Staging Yard — Veterans Pkwy
UPDATE "Location" SET
  "latitude" = 39.4721,
  "longitude" = -119.7882,
  "geofence" = '[[-119.7902, 39.4711], [-119.7862, 39.4711], [-119.7862, 39.4731], [-119.7902, 39.4731], [-119.7902, 39.4711]]'::jsonb
WHERE "code" = 'LOC-003';

-- LOC-004: Fernley Overflow Yard — US-50 Corridor
UPDATE "Location" SET
  "latitude" = 39.6077,
  "longitude" = -119.2521,
  "geofence" = '[[-119.2541, 39.6067], [-119.2501, 39.6067], [-119.2501, 39.6087], [-119.2541, 39.6087], [-119.2541, 39.6067]]'::jsonb
WHERE "code" = 'LOC-004';
