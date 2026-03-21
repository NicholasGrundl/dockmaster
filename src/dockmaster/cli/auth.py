"""CLI OAuth login flow — localhost callback server + token storage."""


import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

import typer

from dockmaster.cli.config import get_server_url, get_token_path

# Token is considered expired if less than this many seconds remain
_EXPIRY_BUFFER = 30


def _credentials_path() -> Path:
    """Return the path to the stored credentials file."""
    return get_token_path()


def load_token() -> str | None:
    """Load a valid (non-expired) token from disk, or return None."""
    path = _credentials_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        expires_at = data.get("expires_at", 0)
        if time.time() >= expires_at - _EXPIRY_BUFFER:
            return None
        return data.get("token")
    except (json.JSONDecodeError, KeyError):
        return None


def require_token() -> str:
    """Load token or exit with an error message."""
    token = load_token()
    if not token:
        typer.echo("Not logged in. Run `dockmaster login` first.", err=True)
        raise typer.Exit(1)
    return token


def _save_token(token: str, expires_at: float) -> None:
    """Save token and expiry to disk."""
    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": token, "expires_at": expires_at}))


def _delete_token() -> None:
    """Delete stored credentials."""
    path = _credentials_path()
    if path.exists():
        path.unlink()


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the token from the OAuth callback redirect.

    The dockmaster server redirects to ``localhost?token=<JWT>`` after a
    successful OAuth flow. This handler extracts the token from the query
    string and stores it on the class for the CLI to pick up.

    Security: The token arrives in the URL query string, which browsers
    persist in history. To mitigate this, the success page immediately calls
    ``history.replaceState()`` to overwrite the URL in the browser's history
    entry with ``/done``, scrubbing the token before it can be observed or
    persisted. The token is extracted server-side from the inbound request
    before the page is served, so the replaceState does not affect the CLI's
    ability to capture it.
    """

    token: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token_list = params.get("token", [])

        if token_list:
            _CallbackHandler.token = token_list[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<!DOCTYPE html>\n"
                b"<html>\n"
                b"<head>\n"
                b"    <title>Dockmaster</title>\n"
                b'    <script src="https://cdn.tailwindcss.com"></script>\n'
                b"    <script>history.replaceState(null, '', '/done');</script>\n"
                b"</head>\n"
                b'<body class="bg-gray-50 flex items-center justify-center min-h-screen">\n'
                b'    <div class="text-center">\n'
                b'        <h2 class="text-xl font-semibold text-gray-900">Login successful</h2>\n'
                b'        <p class="mt-2 text-gray-600">You can close this tab and return to the terminal.</p>\n'
                b"    </div>\n"
                b"</body>\n"
                b"</html>"
            )
        else:
            error = params.get("error", ["Unknown error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<!DOCTYPE html>\n"
                b"<html>\n"
                b"<head>\n"
                b"    <title>Dockmaster</title>\n"
                b'    <script src="https://cdn.tailwindcss.com"></script>\n'
                b"</head>\n"
                b'<body class="bg-gray-50 flex items-center justify-center min-h-screen">\n'
                b'    <div class="text-center">\n'
                b'        <h2 class="text-xl font-semibold text-red-600">Login failed</h2>\n'
                b'        <p class="mt-2 text-gray-600">' + error.encode() + b"</p>\n"
                b"    </div>\n"
                b"</body>\n"
                b"</html>"
            )

    def log_message(self, format, *args):
        # Suppress default HTTP server logging
        pass


def _run_callback_server() -> tuple[HTTPServer, int]:
    """Start a localhost HTTP server on a dynamic port, return (server, port)."""
    server = HTTPServer(("localhost", 0), _CallbackHandler)
    port = server.server_address[1]
    return server, port


def login_command():
    """Authenticate via browser OAuth flow."""
    server_url = get_server_url()

    # Start localhost callback server (dynamic port)
    server, port = _run_callback_server()
    redirect_uri = f"http://localhost:{port}/callback"

    # Open browser to dockmaster login with redirect_uri
    login_url = f"{server_url}/auth/login?redirect_uri={redirect_uri}"
    typer.echo("Opening browser for login...")
    typer.echo(f"If the browser doesn't open, visit: {login_url}")
    webbrowser.open(login_url)

    # Wait for the callback (single request, then stop)
    _CallbackHandler.token = None
    server_thread = Thread(target=server.handle_request, daemon=True)
    server_thread.start()
    server_thread.join(timeout=120)
    server.server_close()

    token = _CallbackHandler.token
    if not token:
        typer.echo("Login timed out or failed.", err=True)
        raise typer.Exit(1)

    # Decode expiry from JWT (without verification — server already validated)
    import jwt as pyjwt

    try:
        claims = pyjwt.decode(token, options={"verify_signature": False})
        expires_at = claims.get("exp", time.time() + 900)
    except pyjwt.DecodeError:
        expires_at = time.time() + 900

    _save_token(token, expires_at)
    typer.echo("Login successful!")


def logout_command():
    """Delete stored credentials."""
    _delete_token()
    typer.echo("Logged out.")
