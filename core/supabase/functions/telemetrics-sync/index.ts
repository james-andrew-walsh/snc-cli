import { createClient } from "npm:@supabase/supabase-js@2";
import type { OEMTelematicsProvider, TelematicsSnapshotInsert } from "./types.ts";
import { e360Provider } from "./providers/e360.ts";

const INSERT_BATCH_SIZE = 500;

// Registry of available provider implementations keyed by providerKey.
// Add new providers here as they are implemented.
const providerRegistry: Record<string, OEMTelematicsProvider> = {
  e360: e360Provider,
};

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

  // 1. Query enabled providers
  const { data: providers, error: providerErr } = await sb
    .from("TelematicsProvider")
    .select("*")
    .eq("enabled", true);

  if (providerErr) {
    console.error("Failed to query TelematicsProvider:", providerErr.message);
    return new Response(
      JSON.stringify({ error: providerErr.message }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }

  if (!providers || providers.length === 0) {
    console.log("No enabled providers found.");
    return new Response(
      JSON.stringify({ message: "No enabled providers", results: [] }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }

  console.log(`Found ${providers.length} enabled provider(s)`);

  const results: Array<{
    providerKey: string;
    inserted: number;
    error?: string;
  }> = [];

  // 2. Iterate each enabled provider
  for (const providerRow of providers) {
    const key = providerRow.providerKey as string;
    const config = (providerRow.config ?? {}) as Record<string, unknown>;
    const impl = providerRegistry[key];

    if (!impl) {
      const msg = `No implementation found for provider "${key}" — skipping`;
      console.warn(msg);
      results.push({ providerKey: key, inserted: 0, error: msg });
      continue;
    }

    try {
      console.log(`\nSyncing provider: ${key}`);

      // 3. Call the provider's sync function
      const snapshots: TelematicsSnapshotInsert[] = await impl.sync(config);

      if (snapshots.length === 0) {
        console.log(`  [${key}] No snapshots returned.`);
        results.push({ providerKey: key, inserted: 0 });
        continue;
      }

      // 4. Insert snapshots in batches (append-only)
      let inserted = 0;
      for (let i = 0; i < snapshots.length; i += INSERT_BATCH_SIZE) {
        const batch = snapshots.slice(i, i + INSERT_BATCH_SIZE);
        const { error: insertErr } = await sb
          .from("TelematicsSnapshot")
          .insert(batch);

        if (insertErr) {
          console.error(
            `  [${key}] Batch ${Math.floor(i / INSERT_BATCH_SIZE) + 1} insert error:`,
            insertErr.message,
          );
        } else {
          inserted += batch.length;
        }
      }

      console.log(`  [${key}] Inserted ${inserted} snapshots.`);
      results.push({ providerKey: key, inserted });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`  [${key}] Provider sync failed:`, message);
      results.push({ providerKey: key, inserted: 0, error: message });
    }
  }

  const duration = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\nTelemetrics sync complete in ${duration}s`);
  console.log("Results:", JSON.stringify(results));

  return new Response(
    JSON.stringify({ duration: `${duration}s`, results }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
});
