# Change Request PERM-003: CLI Clean Error Handling + Verbose Whoami

**Date:** 2026-04-07
**Status:** Pending — do not implement yet
**Depends on:** PERM-001 (dynamic permissions must be live)

---

## Problem

Two issues:

1. When a user attempts an operation they don't have permission for, they currently receive a raw Python stack trace ending in `APIError: {'message': 'new row violates row-level security policy...'}`. This is confusing and unprofessional.

2. `snc auth whoami` only returns email and role — it doesn't show what the user is actually allowed to do.

---

## What to Build

### 1. Clean RLS Error Handling

In `snc_cli/client.py` (or a shared error handler module), catch `APIError` exceptions where the message contains `violates row-level security policy` and translate them to a clean user-facing message:

```
Error: Your account does not have permission to perform this operation.
       Logged in as: agent-read@snc.app (agent_read)
       Contact your administrator to request access.
```

Implementation: wrap the Supabase call in all command files in a try/except, or add a global error handler in the Typer app.

Preferred approach: add a `handle_api_error(e)` helper in `snc_cli/client.py` that inspects the error and either re-raises (for unexpected errors) or calls `typer.echo()` with a clean message and `raise typer.Exit(code=1)`.

Each command file catches `APIError` and calls `handle_api_error(e)`.

### 2. Verbose `snc auth whoami`

Update `snc auth whoami` to fetch and display the user's full permission set from `user_profiles`:

**Current output:**
```json
{
  "email": "agent-write@snc.app",
  "role": "agent_write"
}
```

**New output (--verbose flag, or always verbose):**
```
Logged in as: agent-write@snc.app (agent_write)

Permissions:
  business-unit:    list, get
  equipment:        list, get, update
  dispatch:         list, get, schedule
  job:              list, get
  location:         list, get
  employee:         list, get
  crew-assignment:  list, get, assign, remove
  telemetry:        update
```

JSON output (default mode):
```json
{
  "email": "agent-write@snc.app",
  "role": "agent_write",
  "permissions": {
    "business-unit": ["list", "get"],
    "equipment": ["list", "get", "update"],
    ...
  }
}
```

Implementation: in `snc_cli/commands/auth.py`, after loading credentials, fetch the user's `user_profiles` row (using the stored JWT to call the Supabase REST API) and include the `permissions` field in the output.

---

## Files Changed

| Scope | Change |
|---|---|
| `snc_cli/client.py` | Add `handle_api_error(e)` helper function |
| `snc_cli/commands/dispatch.py` | Catch APIError, call handle_api_error |
| `snc_cli/commands/equipment.py` | Catch APIError, call handle_api_error |
| `snc_cli/commands/job.py` | Catch APIError, call handle_api_error |
| `snc_cli/commands/location.py` | Catch APIError, call handle_api_error |
| `snc_cli/commands/employee.py` | Catch APIError, call handle_api_error |
| `snc_cli/commands/crew_assignment.py` | Catch APIError, call handle_api_error |
| `snc_cli/commands/business_unit.py` | Catch APIError, call handle_api_error |
| `snc_cli/commands/auth.py` | Update whoami to fetch and display permissions |

---

## Instructions for Claude Code

1. Read `snc_cli/commands/dispatch.py` to see the current pattern for Supabase calls
2. The `APIError` class is from `postgrest.exceptions` — import it where needed
3. The error check should match on `'row-level security policy'` in the error message string
4. For whoami: fetch user profile via `GET /rest/v1/user_profiles?email=eq.{email}&select=role,permissions` using the stored access token
5. The `--human` flag should produce the formatted permissions table; JSON mode (default) should include the permissions object

---

## Validation

1. Log in as `agent-read@snc.app`
2. `snc dispatch schedule ...` → clean error message (no stack trace):
   ```
   Error: Your account does not have permission to perform this operation.
          Logged in as: agent-read@snc.app (agent_read)
   ```
3. `snc auth whoami` → shows email, role, AND full permissions object ✅
4. `snc auth whoami --human` → shows formatted permissions table ✅
5. Log in as `james@amplifyluxury.com`
6. `snc auth whoami` → shows admin role and full permissions ✅
7. All other commands still work normally for permitted operations ✅

## Notes

- The error handler should only intercept RLS policy violations (code 42501). All other APIErrors should still surface as normal errors with their original message.
- If `user_profiles` cannot be fetched in whoami (e.g., permissions column not yet seeded), gracefully fall back to showing just email + role rather than crashing.
