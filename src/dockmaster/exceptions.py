"""Application-level exception handlers.

Catch StarletteHTTPException (not FastAPI's subclass) so we also intercept
errors raised by middleware (e.g. RequireProxyHeadersMiddleware returning raw
502 responses) that bypass FastAPI's exception layer entirely.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from dockmaster.ui.config import load_ui_config, templates

_ERROR_MESSAGES = {
    400: "Bad request",
    403: "Access denied",
    404: "Page not found",
    500: "Something went wrong",
    502: "Bad gateway",
    503: "Service unavailable",
}


async def ui_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Serve a styled HTML error page for /ui/* routes; JSON for everything else."""
    status = exc.status_code
    detail = getattr(exc, "detail", None) or "An error occurred"

    if request.url.path.startswith("/ui/"):
        ui_config = getattr(request.app.state, "ui_config", None)
        if ui_config is None:
            ui_config = load_ui_config(None)
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "ui": ui_config,
                "user": None,
                "is_admin": False,
                "status_code": status,
                "message": _ERROR_MESSAGES.get(status, f"Error {status}"),
                "detail": f"The page {request.url.path} could not be loaded.",
            },
            status_code=status,
        )

    return JSONResponse(status_code=status, content={"detail": detail})
