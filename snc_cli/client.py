"""Supabase client factory with user JWT injection."""

from __future__ import annotations

import os

import typer
from postgrest.exceptions import APIError
from supabase import Client, create_client

from snc_cli.auth import load_credentials, refresh_if_needed

_SUPABASE_URL = os.getenv("SUPABASE_URL")
_SUPABASE_ANON_KEY = os.getenv("SUPABASE_KEY")

if not _SUPABASE_URL or not _SUPABASE_ANON_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY environment variables must be set. "
        "Never hardcode credentials in source code."
    )


def get_supabase_client() -> Client:
    """Create a Supabase client with the logged-in user's JWT.

    Loads stored credentials, refreshes if needed, then injects the
    user session so RLS policies fire with the correct identity.
    """
    creds = load_credentials()
    if creds is None:
        typer.echo("Not logged in. Run 'snc login'.", err=True)
        raise SystemExit(1)

    creds = refresh_if_needed(creds)

    client = create_client(_SUPABASE_URL, _SUPABASE_ANON_KEY)
    client.auth.set_session(creds["access_token"], creds["refresh_token"])
    return client


def handle_api_error(
    e: APIError,
    email: str | None = None,
    role: str | None = None,
) -> None:
    """Translate RLS permission errors into clean user-facing messages.

    For RLS violations (code 42501), prints a friendly error and exits.
    All other APIErrors are re-raised as-is.
    """
    code = getattr(e, "code", None)
    message = str(e)

    if code == "42501" or "row-level security" in message:
        typer.echo("Error: Your account does not have permission to perform this operation.")
        if email and role:
            typer.echo(f"       Logged in as: {email} ({role})")
        typer.echo("       Contact your administrator to request access.")
        raise typer.Exit(code=1)

    raise e
