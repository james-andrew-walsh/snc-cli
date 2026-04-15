import { createClient } from "npm:@supabase/supabase-js@2";
import { XMLParser } from "npm:fast-xml-parser";
import type {
  OEMTelematicsProvider,
  TelematicsSnapshotInsert,
} from "../types.ts";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const JDLINK_TOKEN_URL =
  "https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token";

const AEMP_BASE_PROD = "https://partneraemp.deere.com";
const AEMP_BASE_SANDBOX = "https://sandboxaemp.deere.com";

const STALE_THRESHOLD_MS = 4 * 60 * 60 * 1000; // 4 hours

// ISO 15143-3 XML namespace
const NS = "http://standards.iso.org/iso/15143/-3";

// ---------------------------------------------------------------------------
// JDLink Authentication (OAuth2 refresh_token grant)
// ---------------------------------------------------------------------------

async function getJdlinkToken(
  appId: string,
  secret: string,
  refreshToken: string,
): Promise<string> {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: appId,
    client_secret: secret,
    refresh_token: refreshToken,
  });

  const resp = await fetch(JDLINK_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`JDLink auth failed (${resp.status}): ${text}`);
  }

  const json = await resp.json();
  if (!json.access_token) {
    throw new Error("JDLink auth response missing access_token");
  }
  return json.access_token;
}

// ---------------------------------------------------------------------------
// AEMP Fleet Data Fetching (paginated XML)
// ---------------------------------------------------------------------------

async function fetchFleetPages(
  token: string,
  baseUrl: string,
): Promise<string[]> {
  const pages: string[] = [];
  let pageNumber = 1;

  while (true) {
    if (pageNumber > 1) {
      await new Promise((r) => setTimeout(r, 1500));
    }

    const url = `${baseUrl}/Fleet/${pageNumber}`;
    const resp = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/xml",
      },
    });

    if (!resp.ok) {
      const text = await resp.text();
      if (resp.status === 404 && pageNumber > 1) {
        // No more pages
        break;
      }
      throw new Error(`AEMP Fleet fetch failed (${resp.status}): ${text.slice(0, 200)}`);
    }

    const xml = await resp.text();
    pages.push(xml);

    // Check for next link in the XML
    if (!xml.includes("<rel>next</rel>") && !xml.includes("rel=\"next\"")) {
      break;
    }

    pageNumber++;
  }

  return pages;
}

// ---------------------------------------------------------------------------
// ISO 15143-3 XML Parsing
// ---------------------------------------------------------------------------

interface AEMPEquipment {
  equipmentId: string;
  serialNumber: string;
  model: string;
  oemName: string;
  latitude?: number;
  longitude?: number;
  locationDateTime?: string;
  engineHours?: number;
  engineHoursDateTime?: string;
  idleHours?: number;
  fuelConsumedLitres?: number;
  fuelRemainingPercent?: number;
  defRemainingPercent?: number;
}

function parseFleetXml(xmlPages: string[]): AEMPEquipment[] {
  const parser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: "@_",
    removeNSPrefix: true,
    isArray: (name: string) => name === "Equipment" || name === "Links",
  });

  const equipment: AEMPEquipment[] = [];

  for (const xml of xmlPages) {
    const doc = parser.parse(xml);
    const fleet = doc.Fleet ?? doc;
    const items = fleet.Equipment;

    if (!items) continue;

    const eqList = Array.isArray(items) ? items : [items];

    for (const eq of eqList) {
      const header = eq.EquipmentHeader ?? {};
      const location = eq.Location ?? {};
      const hours = eq.CumulativeOperatingHours ?? {};
      const idle = eq.CumulativeIdleHours ?? {};
      const fuelUsed = eq.FuelUsed ?? {};
      const fuelRemaining = eq.FuelRemaining ?? {};
      const defRemaining = eq.DEFRemaining ?? {};

      // Parse EquipmentID — format may be "PIN:SERIAL" or just the serial
      let equipmentId = String(header.EquipmentID ?? "");
      if (equipmentId.startsWith("PIN:")) {
        equipmentId = equipmentId.slice(4);
      }

      const record: AEMPEquipment = {
        equipmentId,
        serialNumber: String(header.SerialNumber ?? equipmentId),
        model: String(header.Model ?? ""),
        oemName: String(header.OEMName ?? "John Deere"),
        latitude: parseFloat(location.Latitude) || undefined,
        longitude: parseFloat(location.Longitude) || undefined,
        locationDateTime:
          location["@_datetime"] ?? location.DateTime ?? undefined,
        engineHours: parseFloat(hours.Hour) || undefined,
        engineHoursDateTime: hours["@_datetime"] ?? undefined,
        idleHours: parseFloat(idle.Hour) || undefined,
        fuelConsumedLitres:
          parseFloat(fuelUsed.FuelConsumed ?? fuelUsed["#text"]) || undefined,
        fuelRemainingPercent: parseFloat(fuelRemaining.Percent) || undefined,
        defRemainingPercent: parseFloat(defRemaining.Percent) || undefined,
      };

      equipment.push(record);
    }
  }

  return equipment;
}

// ---------------------------------------------------------------------------
// Equipment Matching — map JDLink serial/PIN to our Equipment table
// ---------------------------------------------------------------------------

async function buildSerialToCodeMap(
  supabaseUrl: string,
  serviceRoleKey: string,
): Promise<Map<string, { code: string; hcssId: string | null }>> {
  const sb = createClient(supabaseUrl, serviceRoleKey);
  const { data, error } = await sb
    .from("Equipment")
    .select("code, hcssId, serialNumber, vin");

  if (error) {
    console.error("Failed to load Equipment for serial mapping:", error.message);
    return new Map();
  }

  const map = new Map<string, { code: string; hcssId: string | null }>();
  for (const row of data ?? []) {
    const entry = { code: row.code as string, hcssId: row.hcssId as string | null };
    // Index by serialNumber and VIN for flexible matching
    if (row.serialNumber) {
      map.set(String(row.serialNumber).toUpperCase(), entry);
    }
    if (row.vin) {
      map.set(String(row.vin).toUpperCase(), entry);
    }
  }

  console.log(`  [jdlink] Equipment serial/VIN map: ${map.size} entries`);
  return map;
}

// ---------------------------------------------------------------------------
// Snapshot Mapping
// ---------------------------------------------------------------------------

function mapToSnapshot(
  eq: AEMPEquipment,
  snapshotAt: Date,
  serialMap: Map<string, { code: string; hcssId: string | null }>,
): TelematicsSnapshotInsert | null {
  // Try to match by serial number or equipment ID
  const lookupKey = eq.serialNumber.toUpperCase();
  const match =
    serialMap.get(lookupKey) ?? serialMap.get(eq.equipmentId.toUpperCase());

  if (!match) {
    // Equipment not in our system — skip
    return null;
  }

  // Determine staleness
  let isStale = false;
  if (eq.locationDateTime) {
    try {
      const locDt = new Date(eq.locationDateTime);
      isStale = snapshotAt.getTime() - locDt.getTime() > STALE_THRESHOLD_MS;
    } catch {
      isStale = true;
    }
  }

  // Calculate productive hours (engine hours minus idle hours)
  const productiveHours =
    eq.engineHours != null && eq.idleHours != null
      ? eq.engineHours - eq.idleHours
      : undefined;

  return {
    equipmentCode: match.code,
    equipmentHcssId: match.hcssId ?? undefined,
    latitude: eq.latitude,
    longitude: eq.longitude,
    locationDateTime: eq.locationDateTime,
    isLocationStale: isStale,
    hourMeterReadingInHours: eq.engineHours,
    hourMeterReadingDateTime: eq.engineHoursDateTime,
    hourMeterReadingSource: "jdlink",
    engineStatus: undefined, // AEMP doesn't provide engine on/off status
    engineStatusDateTime: undefined,
    engineStatusAt: undefined,
    idleHours: eq.idleHours,
    productiveHours,
    fuelRemainingPercent: eq.fuelRemainingPercent,
    fuelConsumedLitres: eq.fuelConsumedLitres,
    defRemainingPercent: eq.defRemainingPercent,
    providerKey: "jdlink",
    snapshotAt: snapshotAt.toISOString(),
  };
}

// ---------------------------------------------------------------------------
// JDLink Provider
// ---------------------------------------------------------------------------

export const jdlinkProvider: OEMTelematicsProvider = {
  providerKey: "jdlink",

  async sync(
    _config: Record<string, unknown>,
  ): Promise<TelematicsSnapshotInsert[]> {
    const appId = Deno.env.get("JDLINK_APP_ID");
    const secret = Deno.env.get("JDLINK_SECRET");
    const refreshToken = Deno.env.get("JDLINK_REFRESH_TOKEN");
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    const useSandbox = Deno.env.get("JDLINK_USE_SANDBOX") === "true";

    if (!appId || !secret || !refreshToken) {
      throw new Error(
        "Missing JDLINK_APP_ID, JDLINK_SECRET, or JDLINK_REFRESH_TOKEN",
      );
    }
    if (!supabaseUrl || !serviceRoleKey) {
      throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY");
    }

    const snapshotAt = new Date();
    const baseUrl = useSandbox ? AEMP_BASE_SANDBOX : AEMP_BASE_PROD;

    // 1. Authenticate
    console.log("  [jdlink] Authenticating to John Deere ...");
    const token = await getJdlinkToken(appId, secret, refreshToken);

    // 2. Build equipment serial map for matching
    console.log("  [jdlink] Loading equipment serial/VIN map ...");
    const serialMap = await buildSerialToCodeMap(supabaseUrl, serviceRoleKey);

    // 3. Fetch AEMP fleet data (all pages)
    console.log(`  [jdlink] Fetching AEMP fleet data from ${useSandbox ? "sandbox" : "production"} ...`);
    const xmlPages = await fetchFleetPages(token, baseUrl);
    console.log(`  [jdlink] Fetched ${xmlPages.length} page(s) of XML`);

    // 4. Parse XML
    const allEquipment = parseFleetXml(xmlPages);
    console.log(`  [jdlink] Parsed ${allEquipment.length} equipment records`);

    if (allEquipment.length === 0) {
      return [];
    }

    // 5. Map to snapshots (only matched equipment)
    const snapshots: TelematicsSnapshotInsert[] = [];
    let unmatched = 0;

    for (const eq of allEquipment) {
      const snapshot = mapToSnapshot(eq, snapshotAt, serialMap);
      if (snapshot) {
        snapshots.push(snapshot);
      } else {
        unmatched++;
      }
    }

    const staleCount = snapshots.filter((s) => s.isLocationStale).length;
    const hasGps = snapshots.filter((s) => s.latitude != null).length;
    console.log(
      `  [jdlink] ${snapshots.length} snapshots (${unmatched} unmatched), ${hasGps} with GPS, ${staleCount} stale`,
    );

    return snapshots;
  },
};
