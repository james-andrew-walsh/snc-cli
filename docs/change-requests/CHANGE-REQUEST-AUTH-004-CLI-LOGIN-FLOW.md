# Change Request AUTH-004: CLI Login / Logout / Whoami (OAuth2 Browser Flow)

**Date:** 2026-04-07
**Status:** Pending — do not implement yet
**Depends on:** AUTH-001 (Supabase Auth enabled + users exist), AUTH-003 (/auth/callback page on dashboard must exist)

---

## Problem

The CLI currently uses a hard-coded anon key in environment variables. There is no way to identify which user is running a command, and no way to enforce per-user permissions at the CLI layer. Once RLS is live (AUTH-002), the CLI must present a valid user JWT with every request.

## What to Build

### Three New CLI Commands

**`snc login`** — Interactive OAuth2 browser flow:
1. CLI starts a local HTTP server on a random available port (e.g. 51237)
2. Opens the user's default browser to:
   `https://snc-dashboard.vercel.app/auth/callback?redirect_uri=http://localhost:51237/callback`
3. The dashboard callback page handles the Supabase Auth redirect and passes the access + refresh tokens back to `localhost:<port>/callback`
4. CLI local server receives the tokens, stores them in `~/.snc/credentials` as JSON:
   ```json
   {
     "access_token": "...",
     "refresh_token": "...",
     "expires_at": 1234567890,
     "email": "james@amplifyluxury.com",
     "role": "admin"
   }
   ```
5. CLI prints: `Logged in as james@amplifyluxury.com (admin)`

**`snc logout`** — Clears `~/.snc/credentials`. Prints: `Logged out.`

**`snc whoami`** — Reads `~/.snc/credentials` and prints current user + role. If not logged in, prints: `Not logged in. Run 'snc login'.`

### Token Management

- On every command, the CLI reads `~/.snc/credentials`
- If `expires_at` is within 5 minutes, refresh automatically using Supabase `refresh_token` grant
- If refresh fails (token revoked or expired), print: `Session expired. Run 'snc login'.` and exit with code 1
- If no credentials file exists, print: `Not logged in. Run 'snc login'.` and exit with code 1

### Dashboard Auth Callback Page

A new route at `https://snc-dashboard.vercel.app/auth/callback` that:
1. Receives Supabase auth redirect (access_token in URL fragment)
2. Passes the tokens to the `redirect_uri` query parameter (the local CLI server)
3. Shows a success page: "You are now logged in. You may close this tab."

This page is built in AUTH-003 (Dashboard Login). AUTH-004 depends on it existing.

## Files Changed

| Scope | Change |
|---|---|
| `snc-cli/snc/auth.py` | New module: token storage, refresh logic, credential helpers |
| `snc-cli/snc/commands/auth.py` | New commands: `login`, `logout`, `whoami` |
| `snc-cli/snc/main.py` | Register auth commands; add credential check to command pre-hook |
| `snc-dashboard/src/pages/AuthCallback.tsx` | New page: handles Supabase redirect + passes tokens to local server |
| `snc-dashboard/src/App.tsx` | Add route for `/auth/callback` |

## Validation

1. `snc whoami` with no credentials → prints "Not logged in" message
2. `snc login` → opens browser, completes Supabase auth, saves credentials, prints confirmation
3. `snc whoami` after login → prints `james@amplifyluxury.com (admin)`
4. `snc logout` → credentials deleted
5. `snc whoami` after logout → prints "Not logged in" message
6. Token expiry: manually expire token, run any command → auto-refresh works silently
7. Revoked token: manually delete from Supabase, run any command → prints "Session expired" and exits cleanly

## Notes

- `~/.snc/credentials` should have file permissions 600 (owner read/write only). The CLI should set this on write.
- The local HTTP server opened during `snc login` should have a 5-minute timeout — if the user doesn't complete auth in 5 minutes, it closes and prints an error.
- Non-interactive mode (for agents) is handled in AUTH-006, not here. This CR is interactive human login only.
