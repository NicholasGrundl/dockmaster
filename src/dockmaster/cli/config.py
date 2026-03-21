"""CLI configuration — server URL and credential storage paths."""


import os
from pathlib import Path

import platformdirs


def get_server_url() -> str:
    """Return the dockmaster server URL from env or default."""
    return os.environ.get("DOCKMASTER_URL", "http://localhost:8000")


def get_token_path() -> Path:
    """Return the path to the stored credentials file."""
    data_dir = Path(platformdirs.user_data_dir("dockmaster"))
    return data_dir / "credentials.json"
