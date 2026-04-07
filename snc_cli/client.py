"""Supabase client factory with user JWT injection."""

import os

import typer
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
