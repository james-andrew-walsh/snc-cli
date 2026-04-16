-- Fix get_latest_telematics RPC to return latest snapshot per provider

DROP FUNCTION IF EXISTS get_latest_telematics();

CREATE FUNCTION get_latest_telematics()
RETURNS TABLE (
    equipmentCode text,
    latitude double precision,
    longitude double precision,
    locationDateTime timestamptz,
    isLocationStale boolean,
    engineStatus text,
    engineStatusAt timestamptz,
    snapshotAt timestamptz,
    providerKey text,
    hourMeter double precision,
    idleHours double precision,
    fuelRemainingPercent double precision,
    fuelConsumedLiters double precision,
    defRemainingPercent double precision,
    make text,
    model text,
    description text
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (t."equipmentCode", t."providerKey")
        t."equipmentCode",
        t.latitude,
        t.longitude,
        t."locationDateTime",
        t."isLocationStale",
        t."engineStatus",
        t."engineStatusAt",
        t."snapshotAt",
        t."providerKey",
        t."hourMeterReadingInHours" as hourMeter,
        t."idleHours",
        t."fuelRemainingPercent",
        t."fuelConsumedLitres" as fuelConsumedLiters,
        t."defRemainingPercent",
        e.make,
        e.model,
        e.description
    FROM "TelematicsSnapshot" t
    LEFT JOIN "Equipment" e ON e.code = t."equipmentCode"
    WHERE t.latitude IS NOT NULL
    ORDER BY t."equipmentCode", t."providerKey", t."snapshotAt" DESC;
END;
$$ LANGUAGE plpgsql;
