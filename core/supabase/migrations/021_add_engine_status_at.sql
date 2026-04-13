ALTER TABLE "TelematicsSnapshot"
    ADD COLUMN IF NOT EXISTS "engineStatusAt" timestamptz;
