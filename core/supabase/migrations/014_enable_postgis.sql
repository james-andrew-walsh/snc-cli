-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Add geometry column to SiteLocation
ALTER TABLE "SiteLocation"
  ADD COLUMN IF NOT EXISTS "geom" geometry(Polygon, 4326);

-- Populate geom from existing polygon jsonb for any already-saved locations
UPDATE "SiteLocation"
SET "geom" = ST_SetSRID(
  ST_GeomFromGeoJSON(polygon::text),
  4326
)
WHERE polygon IS NOT NULL AND "geom" IS NULL;

-- Spatial index for fast point-in-polygon queries
CREATE INDEX IF NOT EXISTS "SiteLocation_geom_idx"
  ON "SiteLocation" USING GIST ("geom");
