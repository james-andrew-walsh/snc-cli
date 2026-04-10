-- Migration 016: Enrich get_reconciliation_status() with additional fields
-- Returns e360_location, hj_job, hj_job_description, hour_meter, site_id
-- for enriched anomaly detail in map popup and discrepancies table (HCSS-009)

DROP FUNCTION IF EXISTS get_reconciliation_status();

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
  site_id uuid,
  e360_job text,
  e360_location text,
  hj_job text,
  hj_job_description text,
  hour_meter double precision,
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
      "isLocationStale", "engineStatus", "snapshotAt",
      "hourMeterReadingInHours"
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
    SELECT je."equipmentCode",
           (array_agg(DISTINCT je."jobCode"))[1] as "jobCode"
    FROM "JobEquipment" je
    JOIN inside_fence f ON je."jobCode" = ANY(f.site_job_codes)
      AND je."equipmentCode" = f."equipmentCode"
    GROUP BY je."equipmentCode"
  ),
  e360_assign AS (
    SELECT code as "equipmentCode", "jobCode" as e360_job, "locationName" as e360_location
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
    f.site_id,
    e.e360_job,
    e.e360_location,
    h."jobCode" as hj_job,
    j.description as hj_job_description,
    t."hourMeterReadingInHours" as hour_meter,
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
  LEFT JOIN "Job" j ON j.code = h."jobCode"
$$;
