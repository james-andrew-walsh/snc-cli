import { createClient } from "npm:@supabase/supabase-js@2";

// ---------------------------------------------------------------------------
// Future check stubs — implement when data sources become available
// ---------------------------------------------------------------------------

// HOURS_MISMATCH: compare TelematicsSnapshot hourMeter delta vs time card hours
// Stub: log intent, skip — time card data not yet available
async function checkHoursMismatch(): Promise<never[]> {
  console.log("  [stub] checkHoursMismatch — skipped (time card data not available)");
  return [];
}

// IDLE_THRESHOLD: check if idleHours / totalHours > threshold
// Stub: log intent, skip — OEM idle data not yet available
async function checkIdleThreshold(): Promise<never[]> {
  console.log("  [stub] checkIdleThreshold — skipped (OEM idle data not available)");
  return [];
}

// PROVIDER_DISAGREE: compare E360 and JDLink readings for same machine
// Stub: log intent, skip — JDLink not yet provisioned
async function checkProviderDisagreement(): Promise<never[]> {
  console.log("  [stub] checkProviderDisagreement — skipped (JDLink not provisioned)");
  return [];
}

// ---------------------------------------------------------------------------
// Main reconciliation engine
// ---------------------------------------------------------------------------

Deno.serve(async (_req: Request) => {
  const startTime = Date.now();
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

  if (!supabaseUrl || !serviceRoleKey) {
    return new Response(
      JSON.stringify({ error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY" }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }

  const sb = createClient(supabaseUrl, serviceRoleKey);
  let newAnomalyCount = 0;
  let resolvedCount = 0;

  try {
    // -----------------------------------------------------------------
    // 1. Call get_reconciliation_status() RPC — does PostGIS ST_Within +
    //    all joins (latest telematics, E360, HeavyJob) in one query
    // -----------------------------------------------------------------
    const { data: reconRows, error: reconErr } = await sb.rpc(
      "get_reconciliation_status",
    );

    if (reconErr) {
      throw new Error(`get_reconciliation_status RPC failed: ${reconErr.message}`);
    }

    console.log(`get_reconciliation_status returned ${reconRows?.length ?? 0} row(s)`);

    // -----------------------------------------------------------------
    // 2. Load lookup data for enrichment
    // -----------------------------------------------------------------
    const [siteResult, equipResult, jeResult] = await Promise.all([
      // SiteLocation name → id mapping
      sb.from("SiteLocation").select("id, name"),
      // Equipment code → hcssId + locationName
      sb.from("Equipment").select("code, hcssId, locationName"),
      // JobEquipment: equipmentCode → jobCode (for HJ context)
      sb.from("JobEquipment").select("equipmentCode, jobCode"),
    ]);

    if (siteResult.error) throw new Error(`SiteLocation query failed: ${siteResult.error.message}`);
    if (equipResult.error) throw new Error(`Equipment query failed: ${equipResult.error.message}`);
    if (jeResult.error) console.error("JobEquipment query failed:", jeResult.error.message);

    // Build lookup maps
    const siteNameToId = new Map<string, string>();
    for (const s of siteResult.data ?? []) {
      siteNameToId.set(s.name, s.id);
    }

    const equipMap = new Map<string, { hcssId: string | null; locationName: string | null }>();
    for (const e of equipResult.data ?? []) {
      equipMap.set(e.code, { hcssId: e.hcssId, locationName: e.locationName });
    }

    const equipToHjJobs = new Map<string, string[]>();
    for (const je of jeResult.data ?? []) {
      const existing = equipToHjJobs.get(je.equipmentCode) ?? [];
      existing.push(je.jobCode);
      equipToHjJobs.set(je.equipmentCode, existing);
    }

    // -----------------------------------------------------------------
    // 3. Classify each machine — filter to anomalies only
    // -----------------------------------------------------------------
    interface DetectedAnomaly {
      equipmentCode: string;
      equipmentHcssId: string | null;
      siteLocationId: string;
      anomalyType: string;
      e360JobCode: string | null;
      e360LocationName: string | null;
      hjJobCode: string | null;
      hjJobDescription: string | null;
      engineStatus: string | null;
      latitude: number | null;
      longitude: number | null;
    }

    const detected: DetectedAnomaly[] = [];

    for (const row of reconRows ?? []) {
      const status = row.reconciliation_status as string;

      // Map RPC status names to Anomaly table types
      let anomalyType: string | null = null;
      if (status === "ANOMALY") anomalyType = "ANOMALY_NO_HJ";
      else if (status === "DISPUTED") anomalyType = "DISPUTED";
      else if (status === "NOT_IN_EITHER") anomalyType = "NOT_IN_EITHER";

      if (!anomalyType) continue;

      // Resolve siteLocationId from site_name
      const siteName = row.site_name as string | null;
      const siteLocationId = siteName ? siteNameToId.get(siteName) ?? null : null;

      if (!siteLocationId) {
        console.warn(`  Skipping anomaly for ${row.equipmentCode} — could not resolve siteLocationId from "${siteName}"`);
        continue;
      }

      // Enrich from lookup maps
      const equip = equipMap.get(row.equipmentCode as string);
      const hjJobs = equipToHjJobs.get(row.equipmentCode as string) ?? [];

      detected.push({
        equipmentCode: row.equipmentCode as string,
        equipmentHcssId: equip?.hcssId ?? null,
        siteLocationId,
        anomalyType,
        e360JobCode: (row.e360_job as string) ?? null,
        e360LocationName: equip?.locationName ?? null,
        hjJobCode: hjJobs.length > 0 ? hjJobs[0] : null,
        hjJobDescription: null,
        engineStatus: (row.engineStatus as string) ?? null,
        latitude: (row.latitude as number) ?? null,
        longitude: (row.longitude as number) ?? null,
      });
    }

    console.log(`Classified ${detected.length} anomaly(ies)`);

    // -----------------------------------------------------------------
    // 4. Run future check stubs
    // -----------------------------------------------------------------
    await checkHoursMismatch();
    await checkIdleThreshold();
    await checkProviderDisagreement();

    // -----------------------------------------------------------------
    // 5. Load existing active anomalies for dedup + resolution
    // -----------------------------------------------------------------
    const { data: activeAnomalies, error: activeErr } = await sb
      .from("Anomaly")
      .select("id, equipmentCode, siteLocationId, anomalyType")
      .is("resolvedAt", null);

    if (activeErr) {
      console.error("Failed to load active anomalies:", activeErr.message);
    }

    const existingMap = new Map<string, string>(); // composite key → anomaly id
    for (const a of activeAnomalies ?? []) {
      const key = `${a.equipmentCode}|${a.siteLocationId}|${a.anomalyType}`;
      existingMap.set(key, a.id);
    }

    // -----------------------------------------------------------------
    // 6. Create SyncLog entry to get reconciliationRunId
    // -----------------------------------------------------------------
    let reconciliationRunId: string | null = null;
    try {
      const { data: syncLogRow } = await sb
        .from("SyncLog")
        .insert({
          providerKey: "reconciliation",
          providerName: "Reconciliation Engine",
          status: "success",
          rowsInserted: 0,
          durationMs: 0,
          errorMessage: null,
          startedAt: new Date(startTime).toISOString(),
          completedAt: new Date().toISOString(),
        })
        .select("id")
        .single();
      reconciliationRunId = syncLogRow?.id ?? null;
    } catch (logErr) {
      console.error("SyncLog insert failed:", logErr);
    }

    // -----------------------------------------------------------------
    // 7. Determine new anomalies and resolve cleared ones
    // -----------------------------------------------------------------
    const currentKeys = new Set<string>();
    const newAnomalies: Record<string, unknown>[] = [];

    for (const m of detected) {
      const key = `${m.equipmentCode}|${m.siteLocationId}|${m.anomalyType}`;
      currentKeys.add(key);

      if (!existingMap.has(key)) {
        newAnomalies.push({
          equipmentCode: m.equipmentCode,
          equipmentHcssId: m.equipmentHcssId,
          siteLocationId: m.siteLocationId,
          anomalyType: m.anomalyType,
          severity: m.anomalyType === "DISPUTED" ? "error" : "warning",
          e360JobCode: m.e360JobCode,
          e360LocationName: m.e360LocationName,
          hjJobCode: m.hjJobCode,
          hjJobDescription: m.hjJobDescription,
          engineStatus: m.engineStatus,
          hourMeter: null,
          latitude: m.latitude,
          longitude: m.longitude,
          reconciliationRunId,
        });
      }
    }

    // Resolve anomalies no longer detected
    const toResolve: string[] = [];
    for (const [key, id] of existingMap.entries()) {
      if (!currentKeys.has(key)) {
        toResolve.push(id);
      }
    }

    if (toResolve.length > 0) {
      const { error: resolveErr } = await sb
        .from("Anomaly")
        .update({ resolvedAt: new Date().toISOString() })
        .in("id", toResolve);

      if (resolveErr) {
        console.error("Failed to resolve anomalies:", resolveErr.message);
      } else {
        resolvedCount = toResolve.length;
        console.log(`Resolved ${resolvedCount} anomaly(ies)`);
      }
    }

    // -----------------------------------------------------------------
    // 8. Insert new anomalies in batches
    // -----------------------------------------------------------------
    const BATCH_SIZE = 500;
    for (let i = 0; i < newAnomalies.length; i += BATCH_SIZE) {
      const batch = newAnomalies.slice(i, i + BATCH_SIZE);
      const { error: insertErr } = await sb.from("Anomaly").insert(batch);
      if (insertErr) {
        console.error(`Anomaly batch ${Math.floor(i / BATCH_SIZE) + 1} insert error:`, insertErr.message);
      } else {
        newAnomalyCount += batch.length;
      }
    }

    console.log(`Inserted ${newAnomalyCount} new anomaly(ies)`);

    // -----------------------------------------------------------------
    // 9. Update SyncLog entry with final stats + details breakdown
    // -----------------------------------------------------------------
    const anomalyNoHj = newAnomalies.filter(a => a.anomalyType === "ANOMALY_NO_HJ").length;
    const disputed = newAnomalies.filter(a => a.anomalyType === "DISPUTED").length;
    const notInEither = newAnomalies.filter(a => a.anomalyType === "NOT_IN_EITHER").length;

    if (reconciliationRunId) {
      try {
        await sb
          .from("SyncLog")
          .update({
            rowsInserted: newAnomalyCount,
            durationMs: Date.now() - startTime,
            completedAt: new Date().toISOString(),
            details: {
              anomaly_no_hj: anomalyNoHj,
              disputed: disputed,
              not_in_either: notInEither,
              resolved: resolvedCount,
            },
          })
          .eq("id", reconciliationRunId);
      } catch (logErr) {
        console.error("SyncLog update failed:", logErr);
      }
    }

    const duration = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`\nReconciliation complete in ${duration}s — ${newAnomalyCount} new, ${resolvedCount} resolved`);

    return new Response(
      JSON.stringify({ duration: `${duration}s`, newAnomalies: newAnomalyCount, resolved: resolvedCount }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("Reconciliation failed:", message);

    try {
      await sb.from("SyncLog").insert({
        providerKey: "reconciliation",
        providerName: "Reconciliation Engine",
        status: "error",
        rowsInserted: 0,
        durationMs: Date.now() - startTime,
        errorMessage: message,
        startedAt: new Date(startTime).toISOString(),
        completedAt: new Date().toISOString(),
      });
    } catch (logErr) {
      console.error("SyncLog insert failed:", logErr);
    }

    return new Response(
      JSON.stringify({ error: message }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
});
