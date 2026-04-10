# Change Request: ENV-001 — CLI Multi-Environment Support

**Project:** SNC Equipment Tracking  
**Date:** 2026-04-07  
**Status:** DRAFT  
**Implemented by:** Claude Code  
**Depends on:** SETUP-PRODUCTION-ENVIRONMENT.md (production Supabase project must exist)

---

## Problem

The CLI currently has hardcoded Supabase credentials — one URL and one anon key. There is no way to point it at a different Supabase project without manually editing environment variables or config files.

We need the CLI to support two environments:
- **demo** — the current snc-demo Supabase project with sample data
- **prod** — the new snc-production Supabase project with real SNC data

---

## Solution

Add `SNC_ENV` environment variable and `--env` flag support to the CLI. When set to `prod`, the CLI reads production credentials instead of demo credentials. When unset or set to `demo`, it uses the existing demo credentials (preserving backward compatibility).

Credentials for each environment are stored as separate environment variables, both on the developer's machine and in any deployment context.

---

## Changes Required

### `snc_cli/client.py`

Modify `get_supabase_client()` to:
1. Read `SNC_ENV` from the environment (default: `demo`)
2. Based on the value, select the correct URL and key pair:
   - `demo` → `SUPABASE_URL` + `SUPABASE_ANON_KEY` (existing variables, unchanged)
   - `prod` → `SUPABASE_URL_PROD` + `SUPABASE_ANON_KEY_PROD`
3. Raise a clear error if the selected environment's credentials are not found

### `snc_cli/main.py`

Add a global `--env` option to the CLI root group:
- `snc --env prod equipment list`
- When `--env` is passed, override `SNC_ENV` for the duration of that command
- Display the active environment in `snc auth whoami` output

### `snc_cli/commands/auth.py`

Update `whoami` output to include the active environment:
```
{
  "email": "james@amplifyluxury.com",
  "role": "admin",
  "env": "prod"
}
```

### `.env.example` (create if not exists)

Document all required environment variables:
```bash
# Demo environment (default)
SUPABASE_URL=https://[demo-ref].supabase.co
SUPABASE_ANON_KEY=eyJ...

# Production environment
SUPABASE_URL_PROD=https://[prod-ref].supabase.co
SUPABASE_ANON_KEY_PROD=eyJ...

# Active environment (demo or prod, default: demo)
SNC_ENV=demo
```

---

## Credentials Storage

The existing `~/.snc/credentials` file stores the logged-in user's JWT and email. Extend this to be environment-aware:

```json
{
  "demo": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "email": "james@amplifyluxury.com",
    "role": "admin"
  },
  "prod": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "email": "james@amplifyluxury.com",
    "role": "admin"
  }
}
```

`snc auth login` logs into the currently active environment. `snc auth whoami` shows credentials for the active environment. Logging in to `prod` does not affect `demo` credentials and vice versa.

---

## Verification Steps

1. With `SNC_ENV` unset: `snc equipment list` returns demo equipment (5 sample machines)
2. With `SNC_ENV=prod`: `snc equipment list` returns empty (production has no equipment yet)
3. `snc --env prod auth whoami` shows `"env": "prod"`
4. `snc auth login` while in demo environment saves demo credentials only
5. `snc --env prod auth login` saves production credentials independently
6. Switching between environments: `SNC_ENV=demo snc equipment list` and `SNC_ENV=prod snc equipment list` return different data from correct databases

---

## Out of Scope

- Supabase service role key support (that is for the sync script, not the CLI)
- Any changes to the dashboard (see ENV-002)
- HCSS sync logic (see HCSS-001)

