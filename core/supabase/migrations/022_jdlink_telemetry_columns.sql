-- JDLINK-001A: Add JDLink-specific telemetry columns to TelematicsSnapshot
-- and seed JDLink as a telematics provider.

-- New nullable columns for JDLink / ISO 15143-3 fields
ALTER TABLE "TelematicsSnapshot"
    ADD COLUMN IF NOT EXISTS "fuelRemainingPercent" double precision,
    ADD COLUMN IF NOT EXISTS "fuelConsumedLitres" double precision,
    ADD COLUMN IF NOT EXISTS "defRemainingPercent" double precision;

-- Seed JDLink as a provider (disabled by default until credentials are configured)
INSERT INTO "TelematicsProvider" ("name", "providerKey", "enabled", "config")
VALUES ('John Deere JDLink', 'jdlink', false, '{}')
ON CONFLICT ("providerKey") DO NOTHING;
