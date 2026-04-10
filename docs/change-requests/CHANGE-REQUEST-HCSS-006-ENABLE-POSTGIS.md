# Change Request: HCSS-006 — Enable PostGIS + Migrate SiteLocation Polygon

**Project:** SNC Equipment Tracking  
**Date:** 2026-04-09  
**Status:** READY FOR IMPLEMENTATION  
**Depends on:** HCSS-005 ✅ (SiteLocation table exists with polygon jsonb column)

---

## Summary

Enable the PostGIS extension on the Supabase project and migrate the `SiteLocation.polygon` column from jsonb to a proper PostGIS `geometry(Polygon, 4326)` column. This enables all geospatial queries (point-in-polygon, proximity, area) to run in the database rather than in client-side JavaScript or Python scripts.

Without PostGIS, the dashboard cannot determine which machines are inside a geofence. With PostGIS, a single SQL query answers the question for all machines and all geofences simultaneously.

---

## Migration 014: Enable PostGIS + geometry column

**File:** `core/supabase/migrations/014_enable_postgis.sql`

```sql
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
```

---

## Dashboard Change: Write `geom` on Save

When saving a new `SiteLocation` or updating an existing one, the dashboard must also populate the `geom` column alongside the `polygon` jsonb column.

In `src/views/Overview.tsx`, the insert/update for `SiteLocation` should include:
```
geom: `SRID=4326;${wkt_from_polygon}`
```

The easiest approach: keep storing `polygon` as GeoJSON jsonb (for easy frontend rendering), AND store `geom` as WKT so PostGIS can use it for spatial queries.

**Helper function to add to Overview.tsx:**
```typescript
function polygonToWKT(polygon: GeoJSON.Polygon): string {
  const coords = polygon.coordinates[0]
    .map(([lng, lat]) => `${lng} ${lat}`)
    .join(', ')
  return `SRID=4326;POLYGON((${coords}))`
}
```

Pass `geom: polygonToWKT(drawnPolygon)` alongside `polygon: drawnPolygon` in the insert/update.

---

## Verification

1. Migration applied — `SELECT PostGIS_Version();` returns a version string
2. Existing geofences have `geom` populated: `SELECT id, name, geom IS NOT NULL FROM "SiteLocation";`
3. Draw a new geofence, save — verify `geom` column is populated
4. Run a point-in-polygon test query:
```sql
SELECT s.name, COUNT(*) as machines_inside
FROM "SiteLocation" s, (
  SELECT DISTINCT ON ("equipmentCode") "equipmentCode", latitude, longitude
  FROM "TelematicsSnapshot"
  WHERE latitude IS NOT NULL
  ORDER BY "equipmentCode", "snapshotAt" DESC
) t
WHERE ST_Within(
  ST_SetSRID(ST_MakePoint(t.longitude, t.latitude), 4326),
  s.geom
)
GROUP BY s.name;
```
Should return ~42 machines for West 4th Street Corridor.

---

## Notes for Claude Code

- Apply migration via Supabase Management API (SUPABASE_ACCESS_TOKEN, User-Agent: curl/8.1.2)
- Then update src/views/Overview.tsx in the snc-dashboard repo to write `geom` on save/update
- Run npm run build to verify TypeScript clean
- Commit migration file to equipment-tracking repo, dashboard change to snc-dashboard repo
