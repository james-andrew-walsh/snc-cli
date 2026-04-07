"""Token storage, loading, and refresh helpers for CLI auth."""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Optional

import typer

CREDENTIALS_PATH = Path.home() / ".snc" / "credentials"

SUPABASE_URL = "https://ghscnwwatguzmeuabspd.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdoc2Nud3dhdGd1em1ldWFic3BkIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzUyMjc3NjAsImV4cCI6MjA5MDgwMzc2MH0."
    "l50Xlpw5q_HgvbbEg-0mLtx-YkRhV8tDRjecJ6PDnmM"
)

# Refresh if token expires within this many seconds.
REFRESH_WINDOW = 5 * 60


def load_credentials() -> Optional[dict]:
    """Read ~/.snc/credentials and return the parsed JSON, or None."""
    if not CREDENTIALS_PATH.exists():
        return None
    try:
        return json.loads(CREDENTIALS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_credentials(data: dict) -> None:
    """Write credentials JSON to ~/.snc/credentials with mode 600."""
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(json.dumps(data, indent=2))
    os.chmod(CREDENTIALS_PATH, stat.S_IRUSR | stat.S_IWUSR)


def delete_credentials() -> None:
    """Remove the credentials file if it exists."""
    if CREDENTIALS_PATH.exists():
        CREDENTIALS_PATH.unlink()


def refresh_if_needed(creds: dict) -> dict:
    """Auto-refresh the access token if it expires within REFRESH_WINDOW.

    Returns the (possibly updated) credentials dict.
    Exits with code 1 if refresh fails.
    """
    expires_at = creds.get("expires_at", 0)
    if time.time() < expires_at - REFRESH_WINDOW:
        return creds

    # Token is near-expiry or already expired — attempt refresh.
    import httpx

    resp = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Content-Type": "application/json",
        },
        json={"refresh_token": creds["refresh_token"]},
    )

    if resp.status_code != 200:
        typer.echo("Session expired. Run 'snc login'.", err=True)
        raise typer.Exit(code=1)

    body = resp.json()
    creds["access_token"] = body["access_token"]
    creds["refresh_token"] = body["refresh_token"]
    creds["expires_at"] = int(time.time()) + body.get("expires_in", 3600)
    save_credentials(creds)
    return creds


def require_auth() -> dict:
    """Load and return valid credentials, or exit with an error message."""
    creds = load_credentials()
    if creds is None:
        typer.echo("Not logged in. Run 'snc login'.", err=True)
        raise typer.Exit(code=1)
    return refresh_if_needed(creds)
