CREATE TABLE IF NOT EXISTS "SyncLog" (
    "id"            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    "providerKey"   text NOT NULL,           -- "e360", "jdlink", "visionlink", etc.
    "providerName"  text NOT NULL,           -- Human-readable: "Equipment360 (HCSS)"
    "status"        text NOT NULL,           -- "success" | "error"
    "rowsInserted"  integer,                 -- number of TelematicsSnapshot rows written
    "durationMs"    integer,                 -- wall-clock duration of this provider's sync
    "errorMessage"  text,                    -- populated if status = "error"
    "startedAt"     timestamptz NOT NULL,
    "completedAt"   timestamptz NOT NULL DEFAULT now(),
    "createdAt"     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON "SyncLog"("providerKey");
CREATE INDEX ON "SyncLog"("completedAt" DESC);
CREATE INDEX ON "SyncLog"("status");

-- Enable Realtime for dashboard subscription
ALTER PUBLICATION supabase_realtime ADD TABLE "SyncLog";
