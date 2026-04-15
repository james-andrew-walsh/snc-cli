# Change Request: JDLINK-001A-CLI-INTEGRATION

## Objective
Integrate John Deere JDLink API (ISO 15143-3 / AEMP 2.0) into the `snc-cli` backend to provide an additional ground truth telematics source alongside HCSS. Expand the data model to unify all telematics providers into a single table.

## Context
We have secured access to JDLink ISO 15143-3 API, which provides live telemetry for John Deere equipment. Since we expect to add more providers over time (e.g. Caterpillar VisionLink), we need a single `equipment_telemetry` table that stores standardized data from all providers, with nullable columns for provider-specific fields.

## Required Changes

### 1. Database Schema Updates (Supabase Migration)
- Update the existing telematics/telemetry table (or create a new unified one, e.g., `equipment_telemetry`).
- Add a new `provider` column (`TEXT`, e.g., 'JDLink', 'HCSS', 'VisionLink').
- Ensure standard fields exist:
  - `equipment_id` (matched to our core equipment list)
  - `timestamp` (UTC time of the reading)
  - `latitude` (Float)
  - `longitude` (Float)
  - `engine_hours` (Float)
- Add new nullable telemetry fields specific to JDLink/ISO 15143-3 that HCSS may not provide:
  - `idle_hours` (Float)
  - `fuel_remaining_percent` (Float)
  - `fuel_consumed_litres` (Float)
  - `def_remaining_percent` (Float)

### 2. JDLink Edge Function / CLI Sync Command
- Implement an edge function or CLI command `snc sync jdlink` to fetch data.
- **Authentication**:
  - Implement logic to read `JDLINK_APP_ID`, `JDLINK_SECRET`, and `JDLINK_REFRESH_TOKEN` from the environment.
  - Automatically refresh the access token using the stored refresh token via the OAuth2 endpoint (`https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token`).
- **Data Fetching**:
  - Call the AEMP endpoint: `https://partneraemp.deere.com/Fleet/{pageNumber}` (Production) or `sandboxaemp` depending on env.
  - Handle pagination (follow `next` links in the XML response).
  - Parse the ISO 15143-3 XML format using `xml.etree.ElementTree` or similar.
- **Upsert Logic**:
  - Map JDLink PIN/Serial/EquipmentID to our internal `equipment_id`.
  - Upsert records into the unified `equipment_telemetry` table, setting `provider` = 'JDLink'.

### 3. Reconciliation Logic Extension
- Update the reconciliation engine to handle multiple ground truth sources.
- If both HCSS and JDLink provide coordinates/hours for the same machine, establish precedence (e.g., JDLink direct API > HCSS Telematics API).

## Acceptance Criteria
- [ ] Database migration successfully adds new columns and the `provider` field.
- [ ] `snc sync jdlink` command successfully authenticates using the refresh token, parses the XML, and upserts data into Supabase.
- [ ] Telemetry data for JDLink equipment populates with `provider` = 'JDLink' and includes fields like fuel and DEF remaining.
- [ ] The reconciliation engine successfully queries this unified table without breaking existing HCSS anomaly detection.
