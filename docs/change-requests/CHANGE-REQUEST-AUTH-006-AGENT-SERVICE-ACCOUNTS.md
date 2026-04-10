# Change Request AUTH-006: Agent Service Account Support (Non-Interactive Login)

**Date:** 2026-04-07
**Status:** Pending — do not implement yet
**Depends on:** AUTH-005 (CLI JWT integration must be working for human users)

---

## Problem

After AUTH-003/004, the CLI login flow requires a browser — it opens a browser window, waits for a redirect, and stores a token interactively. This is correct for human users but does not work for agents (Bianca running `snc dispatch` from an OpenClaw session, or an anomaly detection agent that runs on a cron schedule with no browser available).

Agents need a way to authenticate non-interactively using credentials stored in environment variables, while still presenting a user JWT so RLS policies apply correctly.

## What to Build

### `snc login --non-interactive` Flag

Extend the `snc login` command to accept non-interactive credentials:

```bash
snc login --non-interactive \
  --email agent-write@snc.app \
  --password $SNC_AGENT_PASSWORD
```

Behavior:
1. Calls `supabase.auth.signInWithPassword({ email, password })` directly (no browser)
2. Stores tokens in `~/.snc/credentials` exactly as the interactive flow does
3. Prints: `Logged in as agent-write@snc.app (agent_write)`
4. Suitable for running at the start of an agent session or in a bootstrap script

### Agent User Accounts to Create (in Supabase Auth + user_profiles)

| Email | Role | Purpose |
|---|---|---|
| `agent-write@snc.app` | `agent_write` | Bianca and other write-capable agents — can dispatch, update equipment status, manage crew |
| `agent-read@snc.app` | `agent_read` | Reconciliation/anomaly detection agents — read-only, cannot modify data |

These accounts are created manually in the Supabase Auth dashboard with strong passwords stored in OpenClaw env vars.

### Environment Variables for Agent Sessions

```bash
SNC_AGENT_EMAIL=agent-write@snc.app
SNC_AGENT_PASSWORD=<stored in openclaw env>
```

Agent bootstrap sequence (added to agent session startup):
```bash
snc login --non-interactive --email $SNC_AGENT_EMAIL --password $SNC_AGENT_PASSWORD
```

After this, all subsequent `snc` commands in the session use the agent JWT automatically (same credential storage path as AUTH-004).

### OpenClaw Env Var Integration

- Add `SNC_AGENT_EMAIL` and `SNC_AGENT_PASSWORD` to OpenClaw's environment configuration
- Add `SNC_AGENT_READ_EMAIL` and `SNC_AGENT_READ_PASSWORD` for read-only agent accounts
- Document in `CORE-CLI-PRD.md` under an "Agent Authentication" section

### Session Lifetime for Agents

Supabase access tokens expire after 1 hour by default. For long-running agent sessions:
- The existing token auto-refresh logic (from AUTH-003) handles this transparently
- Alternatively, Supabase session expiry can be extended in project settings for agent accounts

## Files Changed

| Scope | Change |
|---|---|
| `snc-cli/snc/commands/auth.py` | Add `--non-interactive`, `--email`, `--password` flags to `snc login` |
| Supabase Auth dashboard | Create `agent-write@snc.app` and `agent-read@snc.app` users |
| Supabase `user_profiles` | Seed agent user rows with correct roles |
| OpenClaw env | Add `SNC_AGENT_EMAIL`, `SNC_AGENT_PASSWORD`, `SNC_AGENT_READ_EMAIL`, `SNC_AGENT_READ_PASSWORD` |
| `core/CORE-CLI-PRD.md` | Add Agent Authentication section |

## Validation

1. `snc login --non-interactive --email agent-write@snc.app --password $SNC_AGENT_PASSWORD` → succeeds, credentials stored
2. `snc whoami` → shows `agent-write@snc.app (agent_write)`
3. `snc dispatch schedule ...` → succeeds (INSERT on DispatchEvent allowed for agent_write)
4. `snc equipment create ...` as agent_write → returns 403 (INSERT on Equipment not allowed for agent_write)
5. `snc login --non-interactive --email agent-read@snc.app --password $SNC_AGENT_READ_PASSWORD` → succeeds
6. `snc equipment list` as agent_read → succeeds (SELECT allowed)
7. `snc dispatch schedule ...` as agent_read → returns 403 (INSERT not allowed for agent_read)
8. Non-interactive login fails with bad password → prints clear error and exits with code 1

## Notes

- Do NOT use the Supabase `service_role` key for agents. Service role bypasses RLS entirely. If an agent misbehaves or is compromised, RLS is the safety net. Agent accounts have real roles and real policies.
- The agent email addresses (`agent-write@snc.app`, `agent-read@snc.app`) are service accounts — no human needs to log in with them. Strong auto-generated passwords are appropriate.
- Future: if multiple independent agents need separate audit trails, create one Supabase user per agent rather than sharing `agent-write@snc.app`. For V1, one account per role is sufficient.
- Mo's "inject a problem" scenario: Mo logs in as `dispatcher`, manually inserts a DispatchEvent that mismatches physical reality. The reconciliation agent (logged in as `agent-read`) detects the anomaly and flags it. This works cleanly once all auth CRs are live.
