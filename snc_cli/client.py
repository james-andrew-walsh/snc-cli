"""Supabase client singleton."""

import os

from supabase import Client, create_client

_SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://ghscnwwatguzmeuabspd.supabase.co",
)
_SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdoc2Nud3dhdGd1em1ldWFic3BkIiwi"
    "cm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTIyNzc2MCwiZXhwIjoyMDkw"
    "ODAzNzYwfQ.p1Y083R3ScI5nq3t5C0Z4tLt2ntPxgCAmnRYqbuhNdk",
)

_client: Client | None = None


def get_client() -> Client:
    """Return a cached Supabase client."""
    global _client
    if _client is None:
        _client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return _client
