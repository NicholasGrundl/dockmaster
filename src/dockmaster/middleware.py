"""Security response headers middleware.

Adds standard hardening headers to every HTTP response. These headers protect
against common web vulnerabilities (clickjacking, MIME-type sniffing, XSS)
at the application level, ensuring safe defaults regardless of reverse proxy
configuration.

Headers set:
    X-Content-Type-Options: nosniff
        Prevents browsers from MIME-sniffing the response body. Without this,
        a browser might interpret a JSON response as HTML and execute embedded
        scripts — a classic XSS vector.

    X-Frame-Options: DENY
        Prevents the page from being rendered in an <iframe>. Protects against
        clickjacking attacks where an attacker overlays invisible frames on top
        of the admin UI to capture clicks.

    Content-Security-Policy:
        Controls which resources the browser is allowed to load. Even if an
        attacker injects a <script> tag, the browser won't execute it unless
        the source is explicitly allowlisted. The default policy permits:
        - Scripts from cdn.tailwindcss.com (Tailwind CSS CDN)
        - Images from lh3.googleusercontent.com (Google profile pictures),
          plus data: URIs and self
        - Inline styles (required by Tailwind utility classes and templates)

    Referrer-Policy: strict-origin-when-cross-origin
        Limits how much URL information is sent in the Referer header on
        cross-origin requests. Prevents leaking internal URL paths to
        external services.

NOT set at the app level:
    Strict-Transport-Security (HSTS)
        HSTS tells browsers to refuse plaintext HTTP connections. This is
        dangerous to set at the app level because the app doesn't know whether
        TLS is terminated upstream. Setting HSTS without TLS breaks local
        development and non-TLS environments. Caddy (our reverse proxy) sets
        HSTS automatically when it provisions TLS certificates, so this is
        handled at the infrastructure layer.

Override:
    Set SECURITY_HEADERS=false to disable this middleware entirely. Use this
    when your reverse proxy (Caddy, nginx, etc.) handles all security headers
    and you want to avoid duplicate or conflicting values.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Default CSP policy — allowlists the resources Dockmaster templates use.
# Kept as a module constant so tests can assert against it.
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.tailwindcss.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://lh3.googleusercontent.com; "
    "frame-ancestors 'none'"
)


class RequireProxyHeadersMiddleware(BaseHTTPMiddleware):
    """Returns 502 if X-Forwarded-Proto header is missing.

    Safety net for production behind a reverse proxy: catches the scenario
    where uvicorn's ``--proxy-headers`` flag is forgotten or the proxy isn't
    forwarding headers. Without ``X-Forwarded-Proto``, OAuth callbacks generate
    ``http://`` URLs and secure cookies break.

    Disable with ``REQUIRE_PROXY_HEADERS=false`` for local development
    without a reverse proxy.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if "x-forwarded-proto" not in request.headers:
            return Response(
                content='{"detail":"Missing proxy headers — is the reverse proxy configured?"}',
                status_code=502,
                media_type="application/json",
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security hardening headers to every response.

    See module docstring for full details on each header and the rationale
    for what is (and isn't) included.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = DEFAULT_CSP
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
