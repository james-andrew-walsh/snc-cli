-- Migration 013: SiteLocation + SiteLocationJob (geofence-per-site architecture)
-- Replaces the single-job-code geofence design with a many-to-many site/job model.
-- A SiteLocation is a named physical location with a drawn polygon.
-- SiteLocationJob links a SiteLocation to one or more HCSS job codes.

CREATE TABLE IF NOT EXISTS "SiteLocation" (
    "id"            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "name"          text NOT NULL,
    "description"   text,
    "centerLat"     double precision,
    "centerLng"     double precision,
    "polygon"       jsonb,
    "radiusMeters"  integer,
    "createdBy"     uuid,
    "createdAt"     timestamptz NOT NULL DEFAULT now(),
    "updatedAt"     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "SiteLocationJob" (
    "id"              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "siteLocationId"  uuid NOT NULL REFERENCES "SiteLocation"("id") ON DELETE CASCADE,
    "jobHcssId"       uuid,
    "jobCode"         text NOT NULL,
    "jobDescription"  text,
    "createdAt"       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON "SiteLocationJob"("siteLocationId");
CREATE INDEX ON "SiteLocationJob"("jobCode");
