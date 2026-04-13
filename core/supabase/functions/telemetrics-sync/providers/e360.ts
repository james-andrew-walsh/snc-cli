import { createClient } from "npm:@supabase/supabase-js@2";
import type {
  OEMTelematicsProvider,
  TelematicsSnapshotInsert,
} from "../types.ts";

const HCSS_TOKEN_URL = "https://api.hcssapps.com/identity/connect/token";
const TELEMATICS_BASE = "https://api.hcssapps.com/telematics/api/v1";

const HCSS_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const STALE_THRESHOLD_MS = 4 * 60 * 60 * 1000; // 4 hours

/** Obtain an OAuth2 access token from HCSS (client_credentials grant). */
async function getHcssToken(
  clientId: string,
  clientSecret: string,
): Promise<string> {
  const body = new URLSearchParams({
    grant_type: "client_credentials",
    client_id: clientId,
    client_secret: clientSecret,
    scope: "telematics:read",
  });

  const resp = await fetch(HCSS_TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": HCSS_USER_AGENT,
    },
    body,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`HCSS auth failed (${resp.status}): ${text}`);
  }

  const json = await resp.json();
  if (!json.access_token) {
    throw new Error("HCSS auth response missing access_token");
  }
  return json.access_token;
}

/** GET with automatic retry on 429 rate-limit responses. */
async function getWithRetry(
  url: string,
  headers: Record<string, string>,
  params?: Record<string, string>,
  retries = 8,
): Promise<Response> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  let resp: Response | undefined;

  for (let attempt = 0; attempt < retries; attempt++) {
    resp = await fetch(url + qs, { headers });
    if (resp.status !== 429) return resp;

    let wait = 2000;
    const text = await resp.text();
    const match = text.match(/(\d+) second/);
    if (match) {
      wait = (parseInt(match[1], 10) + 1) * 1000;
    }
    if (attempt < retries - 1) {
      await new Promise((r) => setTimeout(r, wait));
    }
  }

  return resp!;
}

/** Fetch all telematics equipment records (paginated). */
async function fetchTelematics(
  token: string,
): Promise<Record<string, unknown>[]> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "User-Agent": HCSS_USER_AGENT,
    Accept: "application/json",
  };

  const allRecords: Record<string, unknown>[] = [];
  let params: Record<string, string> | undefined;
  let page = 0;

  while (true) {
    if (page > 0) {
      await new Promise((r) => setTimeout(r, 1500));
    }
    page++;

    const resp = await getWithRetry(
      `${TELEMATICS_BASE}/equipment`,
      headers,
      params,
    );
    if (!resp.ok) {
      const text = await resp.text();
      console.error(
        `Telematics fetch failed (${resp.status}): ${text.slice(0, 200)}`,
      );
      break;
    }

    const body = await resp.json();

    // API may return a plain array or a wrapped object
    if (Array.isArray(body)) {
      allRecords.push(...body);
      break;
    }

    // Try known wrapper keys
    let pageData: Record<string, unknown>[] | null = null;
    for (const key of ["results", "data", "items", "value"]) {
      if (key in body && Array.isArray(body[key])) {
        pageData = body[key];
        break;
      }
    }
    if (!pageData) pageData = [];
    allRecords.push(...pageData);

    const nextCursor = body.next as string | undefined;
    if (!nextCursor || pageData.length === 0) break;
    params = { cursor: nextCursor };
  }

  console.log(
    `  Telematics: ${allRecords.length} total, ${allRecords.filter((r) => r.lastLatitude != null).length} with GPS`,
  );
  return allRecords;
}

/** Build a mapping of equipment code -> hcssId from the Equipment table. */
async function buildEquipmentCodeMap(
  supabaseUrl: string,
  serviceRoleKey: string,
): Promise<Map<string, string>> {
  const sb = createClient(supabaseUrl, serviceRoleKey);
  const { data, error } = await sb
    .from("Equipment")
    .select("code,hcssId");

  if (error) {
    console.error("Failed to load Equipment code map:", error.message);
    return new Map();
  }

  const codeMap = new Map<string, string>();
  for (const row of data ?? []) {
    if (row.code && row.hcssId) {
      codeMap.set(row.code, row.hcssId);
    }
  }
  console.log(`  Equipment code map: ${codeMap.size} codes`);
  return codeMap;
}

/** Map a telematics API record to a TelematicsSnapshotInsert. */
function mapSnapshot(
  r: Record<string, unknown>,
  snapshotAt: Date,
  codeMap: Map<string, string>,
): TelematicsSnapshotInsert {
  const code = (r.code as string) ?? "";

  const locationDtStr = r.lastLocationDateTime as string | undefined;
  let isStale = false;
  if (locationDtStr) {
    try {
      const locationDt = new Date(locationDtStr);
      isStale = snapshotAt.getTime() - locationDt.getTime() > STALE_THRESHOLD_MS;
    } catch {
      isStale = true;
    }
  }

  return {
    equipmentCode: code,
    equipmentHcssId: codeMap.get(code),
    latitude: r.lastLatitude as number | undefined,
    longitude: r.lastLongitude as number | undefined,
    locationDateTime: locationDtStr,
    isLocationStale: isStale,
    hourMeterReadingInHours: r.lastHourMeterReadingInHours as
      | number
      | undefined,
    hourMeterReadingDateTime: r.lastHourMeterReadingDateTime as
      | string
      | undefined,
    hourMeterReadingSource: r.lastHourMeterReadingSource as string | undefined,
    engineStatus: r.lastEngineStatus as string | undefined,
    engineStatusDateTime: r.lastEngineStatusDateTime as string | undefined,
    engineStatusAt: r.lastEngineStatusDateTime as string | undefined,
    providerKey: "e360",
    snapshotAt: snapshotAt.toISOString(),
  };
}

// ---------------------------------------------------------------------------
// E360 Provider
// ---------------------------------------------------------------------------

export const e360Provider: OEMTelematicsProvider = {
  providerKey: "e360",

  async sync(_config: Record<string, unknown>): Promise<TelematicsSnapshotInsert[]> {
    const clientId = Deno.env.get("HCSS_CLIENT_ID");
    const clientSecret = Deno.env.get("HCSS_CLIENT_SECRET");
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!clientId || !clientSecret) {
      throw new Error("Missing HCSS_CLIENT_ID or HCSS_CLIENT_SECRET");
    }
    if (!supabaseUrl || !serviceRoleKey) {
      throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY");
    }

    const snapshotAt = new Date();

    // 1. Authenticate to HCSS
    console.log("  [e360] Authenticating to HCSS ...");
    const token = await getHcssToken(clientId, clientSecret);

    // 2. Build equipment code map for HCSS ID lookups
    console.log("  [e360] Loading equipment code map ...");
    const codeMap = await buildEquipmentCodeMap(supabaseUrl, serviceRoleKey);

    // 3. Fetch telematics data
    console.log("  [e360] Fetching telematics data ...");
    const records = await fetchTelematics(token);

    if (records.length === 0) {
      console.log("  [e360] No telematics records returned.");
      return [];
    }

    // 4. Map to snapshot rows
    const snapshots = records.map((r) => mapSnapshot(r, snapshotAt, codeMap));

    const staleCount = snapshots.filter((s) => s.isLocationStale).length;
    const hasGps = snapshots.filter((s) => s.latitude != null).length;
    console.log(
      `  [e360] ${snapshots.length} snapshots, ${hasGps} with GPS, ${staleCount} stale`,
    );

    return snapshots;
  },
};
