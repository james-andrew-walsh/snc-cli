"""Supabase client singleton."""

import os

from supabase import Client, create_client
from typing import Optional

_SUPABASE_URL = os.getenv("SUPABASE_URL")
_SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not _SUPABASE_URL or not _SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY environment variables must be set. "
        "Never hardcode credentials in source code."
    )

_client: Optional[Client] = None


def get_client() -> Client:
    """Return a cached Supabase client."""
    global _client
    if _client is None:
        _client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return _client
