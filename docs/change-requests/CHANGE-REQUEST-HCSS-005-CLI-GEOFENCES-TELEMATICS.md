# Change Request: HCSS-005 — CLI for Geofences and Telematics

**Project:** SNC Equipment Tracking  
**Date:** 2026-04-08  
**Status:** DRAFT  
**Depends on:** HCSS-003 (TelematicsSnapshot table), HCSS-004 (JobGeofence table)

---

## Summary

Extend the `snc` CLI with commands for geofences, telematics history, and reconciliation. Agents and operators need CLI access to everything the dashboard provides — no operation should require the web UI.

---

## New CLI Commands

### `snc sync hcss`

Extend existing sync command with flags:

```bash
snc sync hcss                    # Sync jobs, equipment, locations (HCSS-001)
snc sync hcss --telematics       # Also pull telematics snapshot (HCSS-003)
snc sync hcss --dry-run          # Preview what would sync without writing
snc sync hcss --all              # Full sync: core + telematics
```

---

### `snc geofence`

Manage job geofences.

```bash
snc geofence list                          # List all jobs with geofence status
snc geofence list --missing               # List jobs with no geofence set
snc geofence get <job-code>               # Show geofence for a job
snc geofence set <job-code> \
  --lat <float> --lng <float> \
  --radius <meters>                        # Set circular geofence for a job
snc geofence delete <job-code>            # Remove geofence
```

**Output (list):**
```
Job Code  Description                      Geofence
11062     UNITED TMWA OFFSITES - NVC       Not set
11597     SIERRACON - SUNNYSIDE - CA       38.5234, -121.4567 (radius: 500m)
11613     COR-2023 SEWER MAINTENANCE       Not set
```

---

### `snc telemetry`

Query telematics snapshots.

```bash
snc telemetry list                         # Latest snapshot for all equipment
snc telemetry list --active               # Only equipment with active engine status
snc telemetry get <equipment-code>        # Latest snapshot for one machine
snc telemetry history <equipment-code>    # All snapshots for one machine
snc telemetry history <equipment-code> \
  --since 2026-04-07                       # Snapshots since a date
snc telemetry delta <equipment-code>      # Engine hours delta (last 2 snapshots)
```

**Output (get):**
```
Equipment:  7762 — 21 JD 210L SKIP LOADER
Location:   39.455167, -119.794083
As of:      2026-04-08 18:54 UTC
Hour meter: 3,326.35 hrs
Engine:     Active (last active: 2026-03-06)
```

**Output (delta):**
```
Equipment:  7762 — 21 JD 210L SKIP LOADER
Period:     2026-04-07 06:00 → 2026-04-08 06:00
Hours run:  4.2 hrs
Start loc:  39.455167, -119.794083
End loc:    39.455167, -119.794083
Movement:   None detected
```

---

### `snc reconcile`

Run and query reconciliation results (depends on HCSS-006).

```bash
snc reconcile run                          # Run reconciliation now
snc reconcile run --job <job-code>        # Run for one job only
snc reconcile list                         # List recent anomalies
snc reconcile list --severity critical    # Filter by severity
snc reconcile list --job <job-code>       # Filter by job
snc reconcile get <anomaly-id>            # Full detail on one anomaly
```

**Output (list):**
```
ID        Job    Equipment  Type                    Severity  Detected
a001      11062  7762       Location mismatch        WARNING   2026-04-08
a002      11597  9042       Idle rental (3 days)     CRITICAL  2026-04-07
a003      11613  8019       Hours discrepancy (4h)   WARNING   2026-04-08
```

---

## Implementation Notes

- All new commands follow existing patterns: JSON output by default, `--human` for readable
- Geofence and telemetry commands require `agent_read` scope minimum; `set`/`delete` require `dispatcher` or `admin`
- `snc reconcile run` requires `agent_write` scope
- Error handling follows PERM-003 pattern — clean messages, no stack traces

---

## Verification Steps

1. Run `snc geofence list --missing` — should show all 235 active jobs (none have geofences yet)
2. Set a geofence: `snc geofence set 11062 --lat 39.455 --lng -119.794 --radius 500`
3. Confirm: `snc geofence get 11062`
4. Run telematics sync: `snc sync hcss --telematics`
5. Check: `snc telemetry get 7762`
6. Check history: `snc telemetry history 7762`
7. Check delta: `snc telemetry delta 7762`
