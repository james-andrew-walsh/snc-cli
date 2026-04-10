# Change Request AUTH-005: Replace Anon Key with User JWT in CLI

**Date:** 2026-04-07
**Status:** Pending — do not implement yet
**Depends on:** AUTH-004 (CLI login flow + credential storage must exist)

---

## Problem

After AUTH-003, the CLI can log in and store a user JWT. But all existing CLI commands still build their Supabase client using the anon key from environment variables (`SUPABASE_KEY`). The JWT is stored but not used. RLS policies won't fire correctly until the CLI passes the user's access token as the Authorization header on every request.

## What to Build

### Update Supabase Client Construction in CLI

Currently all commands create the Supabase client like this:
```python
from supabase import create_client
client = create_client(SUPABASE_URL, SUPABASE_KEY)  # anon key
```

After this CR, the client factory checks for stored credentials first:
```python
def get_supabase_client():
    creds = load_credentials()  # from ~/.snc/credentials
    if creds:
        # Use user JWT — RLS will fire with user's identity
        client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        client.auth.set_session(creds["access_token"], creds["refresh_token"])
        return client
    else:
        # No credentials — fail with helpful message
        print("Not logged in. Run 'snc login'.")
        raise SystemExit(1)
```

The anon key is still needed as the API gateway credential — it stays in env vars. The user JWT is layered on top via `set_session`, which causes PostgREST to see `auth.uid()` as the logged-in user and apply RLS accordingly.

### Environment Variable Cleanup

`SUPABASE_KEY` remains required (it is the anon key, needed to initialize the client). No other credential env vars are needed for human users after AUTH-003/004.

`SUPABASE_KEY` should be renamed to `SUPABASE_ANON_KEY` in code (internal variable name only) for clarity — it is not a secret admin key. The actual env var name stays `SUPABASE_KEY` to avoid breaking existing setups.

### Error Handling

- If credentials are present but the access token is expired → auto-refresh (same logic as AUTH-003)
- If refresh fails → `Session expired. Run 'snc login'.`
- If no credentials → `Not logged in. Run 'snc login'.`
- These checks happen before any command executes, via the pre-hook added in AUTH-003

## Files Changed

| Scope | Change |
|---|---|
| `snc-cli/snc/client.py` | New module (or update existing): `get_supabase_client()` factory with JWT injection |
| All command files | Replace direct `create_client()` calls with `get_supabase_client()` |

## Validation

1. Log in as `admin` user → all existing commands work exactly as before
2. Log in as `dispatcher` user → `snc dispatch schedule` succeeds; `snc equipment create` returns 403
3. Log in as `read_only` user → `snc equipment list` succeeds; `snc dispatch schedule` returns 403
4. Not logged in → any command prints "Not logged in" and exits cleanly
5. `snc equipment list` output is identical before and after this CR (for admin user)

## Notes

- This CR should not change any command behavior for admin users — it is purely a plumbing change.
- After this CR, the `SUPABASE_KEY` env var is still required. It is not a secret (it is the public anon key). The user JWT is the actual authentication credential, stored in `~/.snc/credentials`.
- AUTH-006 (agent non-interactive login) will add a bypass path so agents can authenticate without the browser flow. That is handled separately.
