CREATE TABLE IF NOT EXISTS "TelematicsSnapshot" (
    "id"                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "equipmentCode"               text NOT NULL,
    "equipmentHcssId"             uuid,
    "latitude"                    double precision,
    "longitude"                   double precision,
    "locationDateTime"            timestamptz,
    "isLocationStale"             boolean NOT NULL DEFAULT false,
    "hourMeterReadingInHours"     double precision,
    "hourMeterReadingDateTime"    timestamptz,
    "hourMeterReadingSource"      text,
    "engineStatus"                text,
    "engineStatusDateTime"        timestamptz,
    "snapshotAt"                  timestamptz NOT NULL DEFAULT now(),
    "createdAt"                   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON "TelematicsSnapshot"("equipmentCode");
CREATE INDEX ON "TelematicsSnapshot"("snapshotAt");
CREATE INDEX ON "TelematicsSnapshot"("isLocationStale");
