"""auth commands — login, logout, whoami."""

from __future__ import annotations

import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import typer

from snc_cli.auth import (
    SUPABASE_ANON_KEY,
    SUPABASE_URL,
    delete_credentials,
    load_credentials,
    save_credentials,
)

DASHBOARD_CALLBACK = "https://snc-dashboard.vercel.app/auth/callback"
LOGIN_TIMEOUT = 300  # 5 minutes

app = typer.Typer(name="auth", help="Authentication commands.")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@app.command("login")
def login() -> None:
    """Log in via browser-based OAuth2 flow."""
    result: dict = {}
    error: list[str] = []

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            qs = parse_qs(urlparse(self.path).query)
            access_token = qs.get("access_token", [None])[0]
            refresh_token = qs.get("refresh_token", [None])[0]
            expires_in = qs.get("expires_in", ["3600"])[0]

            if not access_token or not refresh_token:
                error.append("Missing tokens in callback.")
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Login failed.</h1>")
                return

            result["access_token"] = access_token
            result["refresh_token"] = refresh_token
            result["expires_at"] = int(time.time()) + int(expires_in)

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h1>Login successful!</h1><p>You may close this tab.</p>"
            )

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # silence request logs

    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    port = server.server_address[1]

    url = f"{DASHBOARD_CALLBACK}?redirect_uri=http://localhost:{port}/callback"
    typer.echo(f"Opening browser for login…\n  {url}")
    webbrowser.open(url)

    # Run the server in a thread so we can enforce a timeout.
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()
    server_thread.join(timeout=LOGIN_TIMEOUT)
    server.server_close()

    if error:
        typer.echo(f"Login failed: {error[0]}", err=True)
        raise typer.Exit(code=1)

    if not result:
        typer.echo("Login timed out. Please try again.", err=True)
        raise typer.Exit(code=1)

    # Fetch user profile from Supabase to get email + role.
    import httpx

    profile_resp = httpx.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {result['access_token']}",
        },
    )

    email = "unknown"
    role = "unknown"
    if profile_resp.status_code == 200:
        user_data = profile_resp.json()
        email = user_data.get("email", "unknown")

    # Look up role from user_profiles table.
    profiles_resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/user_profiles?email=eq.{email}&select=role",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {result['access_token']}",
        },
    )
    if profiles_resp.status_code == 200:
        rows = profiles_resp.json()
        if rows:
            role = rows[0].get("role", "unknown")

    result["email"] = email
    result["role"] = role
    save_credentials(result)

    typer.echo(f"Logged in as {email} ({role})")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@app.command("logout")
def logout() -> None:
    """Clear saved credentials."""
    delete_credentials()
    typer.echo("Logged out.")


# ---------------------------------------------------------------------------
# Whoami
# ---------------------------------------------------------------------------


@app.command("whoami")
def whoami() -> None:
    """Show the currently logged-in user."""
    creds = load_credentials()
    if creds is None:
        typer.echo("Not logged in. Run 'snc login'.")
        raise typer.Exit(code=0)
    typer.echo(json.dumps({"email": creds.get("email"), "role": creds.get("role")}, indent=2))
