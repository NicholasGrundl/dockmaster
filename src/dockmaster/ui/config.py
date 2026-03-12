"""UI theme and branding configuration.

Loaded from a JSON file if ``UI_CONFIG_PATH`` is set in the environment,
otherwise sensible defaults are used.  The config is attached to
``app.state.ui_config`` during lifespan startup.

Example JSON file::

    {
        "brand_name": "Acme Auth",
        "primary_color": "#0d6efd",
        "accent_color": "#198754",
        "logo_url": "/static/logo.png",
        "footer_text": "Acme Corp \u00b7 Internal Use Only"
    }
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from pydantic import BaseModel

log = structlog.get_logger("dockmaster.ui")


class UIConfig(BaseModel):
    """Theme and branding settings for the admin UI."""

    brand_name: str = "Dockmaster"
    primary_color: str = "#1a73e8"
    accent_color: str = "#198754"
    text_color: str = "#1f2937"
    bg_color: str = "#f9fafb"
    surface_color: str = "#ffffff"
    border_color: str = "#e5e7eb"
    logo_url: str | None = None
    footer_text: str = "Dockmaster Auth Service"


def load_ui_config(path: str | None = None) -> UIConfig:
    """Load UIConfig from a JSON file, falling back to defaults.

    Parameters
    ----------
    path:
        File path to a JSON config file.  If *None* or the file does not
        exist, default values are used.
    """
    if not path:
        log.info("ui_config_loaded", source="defaults")
        return UIConfig()

    config_path = Path(path)
    if not config_path.is_file():
        log.warning("ui_config_file_not_found", path=path)
        return UIConfig()

    try:
        data = json.loads(config_path.read_text())
        config = UIConfig(**data)
        log.info("ui_config_loaded", source=str(config_path), brand=config.brand_name)
        return config
    except (json.JSONDecodeError, ValueError) as exc:
        log.error("ui_config_parse_error", path=path, error=str(exc))
        return UIConfig()
