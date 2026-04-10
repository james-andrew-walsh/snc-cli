-- TelematicsProvider registry
CREATE TABLE IF NOT EXISTS "TelematicsProvider" (
    "id"          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "name"        text NOT NULL,
    "providerKey" text NOT NULL UNIQUE,
    "enabled"     boolean NOT NULL DEFAULT true,
    "config"      jsonb NOT NULL DEFAULT '{}',
    "createdAt"   timestamptz NOT NULL DEFAULT now(),
    "updatedAt"   timestamptz NOT NULL DEFAULT now()
);

-- Add providerKey to TelematicsSnapshot
ALTER TABLE "TelematicsSnapshot"
    ADD COLUMN IF NOT EXISTS "providerKey" text,
    ADD COLUMN IF NOT EXISTS "idleHours" double precision,
    ADD COLUMN IF NOT EXISTS "productiveHours" double precision;

CREATE INDEX IF NOT EXISTS idx_telematics_snapshot_provider_key ON "TelematicsSnapshot"("providerKey");

-- Seed E360 as the first provider
INSERT INTO "TelematicsProvider" ("name", "providerKey", "enabled", "config")
VALUES ('Equipment360 (HCSS)', 'e360', true, '{}')
ON CONFLICT ("providerKey") DO NOTHING;
