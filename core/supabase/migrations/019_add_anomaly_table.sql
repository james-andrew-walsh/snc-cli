-- Drop and replace any existing Anomaly table stub
DROP TABLE IF EXISTS "Anomaly";

CREATE TABLE "Anomaly" (
    "id"                uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    "equipmentCode"     text NOT NULL,
    "equipmentHcssId"   uuid,
    "siteLocationId"    uuid REFERENCES "SiteLocation"("id") ON DELETE SET NULL,

    -- Classification
    "anomalyType"       text NOT NULL,
    -- Current types:
    --   ANOMALY_NO_HJ      — E360 assigns here, HeavyJob has no authorization record
    --   DISPUTED           — E360 and HeavyJob disagree on job code
    --   NOT_IN_EITHER      — engine active, GPS on site, no record in E360 or HJ
    --   HOURS_MISMATCH     — (future) GPS engine hours don't match time card
    --   IDLE_THRESHOLD     — (future) machine idle > X% of reported hours
    --   PROVIDER_DISAGREE  — (future) E360 and JDLink report different hours
    "severity"          text NOT NULL DEFAULT 'warning',
    -- "warning" | "error" | "info"

    -- Context (populated at detection time)
    "e360JobCode"       text,
    "e360LocationName"  text,
    "hjJobCode"         text,
    "hjJobDescription"  text,
    "engineStatus"      text,
    "hourMeter"         double precision,
    "latitude"          double precision,
    "longitude"         double precision,

    -- Lifecycle
    "detectedAt"        timestamptz NOT NULL DEFAULT now(),
    "resolvedAt"        timestamptz,            -- null = still active
    "reconciliationRunId" uuid,                 -- links to the SyncLog entry that found this

    "createdAt"         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON "Anomaly"("equipmentCode");
CREATE INDEX ON "Anomaly"("siteLocationId");
CREATE INDEX ON "Anomaly"("anomalyType");
CREATE INDEX ON "Anomaly"("detectedAt" DESC);
CREATE INDEX ON "Anomaly"("resolvedAt") WHERE "resolvedAt" IS NULL;

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE "Anomaly";
