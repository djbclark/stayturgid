"""Shared FIRERPA service-certificate discovery for Mac-side clients."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CERTIFICATE = Path("~/.config/stayturgid/firerpa.pem").expanduser()


def certificate_path() -> str:
    """Return the configured FIRERPA PEM path, failing closed if it is absent."""
    configured = os.environ.get("FIRERPA_CERTIFICATE", str(DEFAULT_CERTIFICATE))
    path = Path(configured).expanduser()
    if not path.is_file():
        raise FileNotFoundError(
            f"FIRERPA service certificate not found: {path}. "
            "Set FIRERPA_CERTIFICATE or provision ~/.config/stayturgid/firerpa.pem."
        )
    return str(path)
