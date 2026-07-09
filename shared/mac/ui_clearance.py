#!/usr/bin/env python3
"""Mac-path re-export of shared/ui_clearance.py (PiP / overlay clearance)."""
from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from shared.ui_clearance import *  # noqa: F401,F403
from shared.ui_clearance import clear_ui_obstructions  # noqa: F401
