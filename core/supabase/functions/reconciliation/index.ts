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

// PROVIDER_DISAGREE: compare E360 and JDLink readings for same machine.
// When both providers report for the same equipment, JDLink (direct OEM API)
// takes precedence over HCSS/E360.
interface ProviderDisagreement {
  equipmentCode: string;
  equipmentHcssId: string | null;
  e360Hours: number;
  jdlinkHours: number;
  hoursDelta: number;
}

const HOURS_DISAGREE_THRESHOLD = 50; // flag if providers differ by > 50 hours

async function checkProviderDisagreement(
  sb: ReturnType<typeof createClient>,
): Promise<ProviderDisagreement[]> {
  // Get the latest snapshot per equipment per provider (e360 and jdlink only)
  const { data: snapshots, error } = await sb
    .from("TelematicsSnapshot")
    .select("equipmentCode, equipmentHcssId, providerKey, hourMeterReadingInHours, snapshotAt")
    .in("providerKey", ["e360", "jdlink"])
    .not("hourMeterReadingInHours", "is", null)
    .order("snapshotAt", { ascending: false });

  if (error) {
    console.error("  checkProviderDisagreement query failed:", error.message);
    return [];
  }

  if (!snapshots || snapshots.length === 0) {
    console.log("  checkProviderDisagreement — no dual-provider data available");
    return [];
  }

  // Build latest reading per equipment per provider
  const latest = new Map<string, Map<string, { hours: number; hcssId: string | null }>>();

  for (const s of snapshots) {
    const code = s.equipmentCode as string;
    const provider = s.providerKey as string;
    if (!latest.has(code)) latest.set(code, new Map());
    const byProvider = latest.get(code)!;
    // First seen is latest (ordered by snapshotAt DESC)
    if (!byProvider.has(provider)) {
      byProvider.set(provider, {
        hours: s.hourMeterReadingInHours as number,
        hcssId: s.equipmentHcssId as string | null,
      });
    }
  }

  // Compare equipment that has readings from both providers
  const disagreements: ProviderDisagreement[] = [];
  for (const [code, providers] of latest) {
    const e360 = providers.get("e360");
    const jdlink = providers.get("jdlink");
    if (!e360 || !jdlink) continue;

    const delta = Math.abs(e360.hours - jdlink.hours);
    if (delta > HOURS_DISAGREE_THRESHOLD) {
      disagreements.push({
        equipmentCode: code,
        equipmentHcssId: jdlink.hcssId ?? e360.hcssId,
        e360Hours: e360.hours,
        jdlinkHours: jdlink.hours,
        hoursDelta: delta,
      });
    }
  }

  console.log(
    `  checkProviderDisagreement — ${latest.size} equipment with dual providers, ${disagreements.length} disagreement(s)`,
  );
  return disagreements;
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
    // 4. Run additional checks
    // -----------------------------------------------------------------
    await checkHoursMismatch();
    await checkIdleThreshold();
    const providerDisagreements = await checkProviderDisagreement(sb);

    // Add provider disagreements to detected anomalies.
    // These don't have a siteLocationId, so we use a synthetic one.
    for (const d of providerDisagreements) {
      detected.push({
        equipmentCode: d.equipmentCode,
        equipmentHcssId: d.equipmentHcssId,
        siteLocationId: "00000000-0000-0000-0000-000000000000", // synthetic — not site-bound
        anomalyType: "PROVIDER_DISAGREE",
        e360JobCode: null,
        e360LocationName: equipMap.get(d.equipmentCode)?.locationName ?? null,
        hjJobCode: (equipToHjJobs.get(d.equipmentCode) ?? [])[0] ?? null,
        hjJobDescription: null,
        engineStatus: null,
        latitude: null,
        longitude: null,
      });
    }

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
    // 9. Query total active anomaly counts + update SyncLog
    // -----------------------------------------------------------------
    const { data: activeCounts } = await sb
      .from("Anomaly")
      .select("anomalyType")
      .is("resolvedAt", null);

    const totalActive = activeCounts?.length ?? 0;
    const activeNoHj = activeCounts?.filter(a => a.anomalyType === "ANOMALY_NO_HJ").length ?? 0;
    const activeDisputed = activeCounts?.filter(a => a.anomalyType === "DISPUTED").length ?? 0;
    const activeNotInEither = activeCounts?.filter(a => a.anomalyType === "NOT_IN_EITHER").length ?? 0;
    const activeProviderDisagree = activeCounts?.filter(a => a.anomalyType === "PROVIDER_DISAGREE").length ?? 0;

    if (reconciliationRunId) {
      try {
        await sb
          .from("SyncLog")
          .update({
            rowsInserted: newAnomalyCount,
            durationMs: Date.now() - startTime,
            completedAt: new Date().toISOString(),
            details: {
              new_anomalies: newAnomalyCount,
              resolved: resolvedCount,
              total_active: totalActive,
              anomaly_no_hj: activeNoHj,
              disputed: activeDisputed,
              not_in_either: activeNotInEither,
              provider_disagree: activeProviderDisagree,
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
