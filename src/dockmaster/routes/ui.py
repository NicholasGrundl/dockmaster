"""Routes: Test UI — /ui/test."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from itsdangerous import BadSignature, URLSafeSerializer

from dockmaster.config import Settings, get_settings

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@router.get("/test", response_class=HTMLResponse)
async def test_ui(request: Request, settings: Settings = Depends(get_settings)):
    """Serve the test UI page with session state."""
    # Load principal from session cookie (same logic as /auth/principal)
    principal: dict = {}
    session_store = getattr(request.app.state, "session_store", None)
    cookie = request.cookies.get("session_id")
    if cookie and session_store:
        signer = URLSafeSerializer(settings.session_secret_key)
        try:
            session_id = signer.loads(cookie)
            data = await session_store.get(session_id)
            if data:
                principal = data
        except BadSignature:
            pass

    # Render template with simple string replacement
    template = (TEMPLATES_DIR / "login_test.html").read_text()
    rendered = template.replace("{{ principal_json }}", json.dumps(principal, indent=2))

    # Handle Jinja2-style conditionals manually (minimal approach)
    if principal.get("email"):
        rendered = _keep_block(rendered, "principal and principal.email", keep=True)
        rendered = rendered.replace("{{ principal.email }}", principal.get("email", ""))
        rendered = rendered.replace("{{ principal.name }}", principal.get("name", ""))
    else:
        rendered = _keep_block(rendered, "principal and principal.email", keep=False)

    return HTMLResponse(content=rendered)


def _keep_block(html: str, condition: str, keep: bool) -> str:
    """Remove or keep a {% if condition %}...{% else %}...{% endif %} block."""
    if_tag = f"{{% if {condition} %}}"
    else_tag = "{% else %}"
    endif_tag = "{% endif %}"

    if_pos = html.find(if_tag)
    if if_pos == -1:
        return html

    else_pos = html.find(else_tag, if_pos)
    endif_pos = html.find(endif_tag, if_pos)

    if else_pos == -1 or endif_pos == -1:
        return html

    if_content = html[if_pos + len(if_tag) : else_pos]
    else_content = html[else_pos + len(else_tag) : endif_pos]

    chosen = if_content if keep else else_content
    return html[:if_pos] + chosen + html[endif_pos + len(endif_tag) :]
