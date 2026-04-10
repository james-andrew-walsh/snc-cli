-- Migration 015: RPC function get_reconciliation_status()
-- Returns one row per machine with reconciliation_status for map ring indicators
-- Depends on: PostGIS (migration 014), SiteLocation.geom, SiteLocationJob

CREATE OR REPLACE FUNCTION get_reconciliation_status()
RETURNS TABLE (
  "equipmentCode" text,
  latitude double precision,
  longitude double precision,
  "locationDateTime" timestamptz,
  "isLocationStale" boolean,
  "engineStatus" text,
  "snapshotAt" timestamptz,
  site_name text,
  e360_job text,
  reconciliation_status text,
  make text,
  model text,
  description text
)
LANGUAGE sql STABLE
AS $$
  WITH latest_tel AS (
    SELECT DISTINCT ON ("equipmentCode")
      "equipmentCode", latitude, longitude, "locationDateTime",
      "isLocationStale", "engineStatus", "snapshotAt"
    FROM "TelematicsSnapshot"
    WHERE latitude IS NOT NULL
    ORDER BY "equipmentCode", "snapshotAt" DESC
  ),
  inside_fence AS (
    SELECT t."equipmentCode", s.id as site_id, s.name as site_name,
      array_agg(DISTINCT slj."jobCode") as site_job_codes
    FROM latest_tel t
    JOIN "SiteLocation" s ON ST_Within(
      ST_SetSRID(ST_MakePoint(t.longitude, t.latitude), 4326), s.geom
    )
    JOIN "SiteLocationJob" slj ON slj."siteLocationId" = s.id
    GROUP BY t."equipmentCode", s.id, s.name
  ),
  hj_auth AS (
    SELECT DISTINCT je."equipmentCode", je."jobCode"
    FROM "JobEquipment" je
    JOIN inside_fence f ON je."jobCode" = ANY(f.site_job_codes)
      AND je."equipmentCode" = f."equipmentCode"
  ),
  e360_assign AS (
    SELECT code as "equipmentCode", "jobCode" as e360_job
    FROM "Equipment"
  )
  SELECT
    t."equipmentCode",
    t.latitude,
    t.longitude,
    t."locationDateTime",
    t."isLocationStale",
    t."engineStatus",
    t."snapshotAt",
    f.site_name,
    e.e360_job,
    CASE
      WHEN f."equipmentCode" IS NULL THEN 'OUTSIDE'
      WHEN h."equipmentCode" IS NULL AND e.e360_job IS NULL THEN 'NOT_IN_EITHER'
      WHEN h."equipmentCode" IS NULL THEN 'ANOMALY'
      WHEN e.e360_job IS NOT NULL AND NOT (e.e360_job = ANY(f.site_job_codes)) THEN 'DISPUTED'
      ELSE 'OK'
    END as reconciliation_status,
    eq.make,
    eq.model,
    eq.description
  FROM latest_tel t
  LEFT JOIN inside_fence f ON f."equipmentCode" = t."equipmentCode"
  LEFT JOIN hj_auth h ON h."equipmentCode" = t."equipmentCode"
  LEFT JOIN e360_assign e ON e."equipmentCode" = t."equipmentCode"
  LEFT JOIN "Equipment" eq ON eq.code = t."equipmentCode"
$$;
