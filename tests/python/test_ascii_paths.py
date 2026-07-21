"""ASCII-only path policy for on-device deploy targets and AutoJs6 project code."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(
    0,
    str(REPO / "ansible_collections" / "stayturgid" / "android_common" / "plugins" / "module_utils"),
)
import autojs6_deploy_util as util

AUTOJS6 = REPO / "device" / "autojs6"
NON_ASCII = re.compile(r"[^\x00-\x7F]")
# Path-like string literals (absolute or repo-ish) — must be ASCII if present.
PATH_LITERAL = re.compile(
    r"""(?x)
    (?:['"])
    (
      /sdcard/[^'"]+
      | /storage/emulated/[^'"]+
      | /data/data/[^'"]+
      | \./device/[^'"]+
      | stayturgid/[a-zA-Z0-9_./-]+
    )
    (?:['"])
    """
)


def test_default_autojs6_target_is_ascii():
    assert util.DEFAULT_TARGET == "/sdcard/stayturgid/autojs6"
    assert not NON_ASCII.search(util.DEFAULT_TARGET)
    for mirror in util.STALE_PROJECT_MIRRORS:
        # Mirrors may document the Chinese locale folder for removal only;
        # the deploy *target* must stay ASCII.
        assert mirror != util.DEFAULT_TARGET


def test_autojs6_project_source_filenames_ascii():
    for path in AUTOJS6.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            assert not NON_ASCII.search(path.name), "non-ASCII filename: %s" % path


def test_autojs6_js_path_literals_ascii():
    """Hard-coded on-device paths in JS must not introduce non-ASCII segments."""
    bad: list[str] = []
    for path in AUTOJS6.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        for m in PATH_LITERAL.finditer(text):
            lit = m.group(1)
            if NON_ASCII.search(lit):
                bad.append("%s: %s" % (path.relative_to(REPO), lit))
    assert bad == [], "non-ASCII path literals:\n  " + "\n  ".join(bad)


def test_engine_guard_main_is_canonical():
    text = (AUTOJS6 / "lib" / "engine_guard.js").read_text(encoding="utf-8")
    assert 'MAIN = "/sdcard/stayturgid/autojs6/main.js"' in text
