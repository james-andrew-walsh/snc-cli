ALTER TABLE "SyncLog"
    ADD COLUMN IF NOT EXISTS "details" jsonb;
