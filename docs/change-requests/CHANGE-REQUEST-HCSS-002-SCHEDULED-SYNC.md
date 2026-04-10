# Change Request: HCSS-002 — Scheduled Sync

**Project:** SNC Equipment Tracking  
**Date:** 2026-04-08  
**Status:** DRAFT  
**Depends on:** HCSS-001 (must be implemented first)

---

## Summary

Add automated scheduling to the HCSS sync layer. Instead of manual execution, the sync runs automatically on a schedule.

---

## Schedule

**Frequency:** Twice daily  
**Times:** 6:00 AM and 6:00 PM Pacific Time  
**Scope:** Same as HCSS-001 — active jobs, equipment, locations

**Rationale:**
- SNC only needs daily reconciliation, not intraday
- Morning sync captures start-of-day state
- Evening sync captures end-of-day state
- Dashboard shows "as of [timestamp]" — acceptable for daily ops

---

## Implementation Options

### Option A: Cron Job on Mac Mini (Simplest)

```bash
# Crontab entry
0 6,18 * * * cd /path/to/snc_cli && python scripts/hcss_sync.py >> /var/log/snc-sync.log 2>&1
```

**Pros:**
- Simple to set up
- Uses existing sync script from HCSS-001
- Logs to local file for debugging

**Cons:**
- Requires Mac mini to be running
- No centralized logging
- Manual intervention if job fails

### Option B: Supabase Edge Function (Cloud)

Create a Supabase Edge Function that runs on a schedule using pg_cron.

**Pros:**
- Cloud-based, no local machine dependency
- Integrated with Supabase
- Built-in logging

**Cons:**
- More complex setup
- Requires Edge Function deployment
- May need separate HCSS credential management

### Option C: GitHub Actions (CI-based)

GitHub Actions workflow running on schedule.

**Pros:**
- Version controlled
- GitHub-hosted runners
- Easy to monitor

**Cons:**
- Overkill for this use case
- Potential rate limits
- External dependency on GitHub

---

## Recommended: Option A (Cron)

For initial implementation, use cron on the Mac mini. Simple, reliable, uses what we already have.

---

## Implementation Steps

1. **Verify HCSS-001 is complete** — Sync script works manually
2. **Add logging** — Ensure sync script outputs to stdout/stderr with timestamps
3. **Create cron entry** — Add to crontab with proper PATH and environment
4. **Test** — Verify cron runs, check logs
5. **Monitor** — Check `/var/log/snc-sync.log` periodically

---

## Monitoring & Alerting

**Log location:** `/var/log/snc-sync.log`

**What to monitor:**
- Sync failures (non-zero exit code)
- Unexpected record count changes
- HCSS API errors

**Future enhancement:** Add alerting (email/Slack) on sync failure.

---

## Rollback

To disable scheduled sync:
```bash
crontab -e
# Remove or comment out the sync entry
```

Manual sync remains available via CLI.
