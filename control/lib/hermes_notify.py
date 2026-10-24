"""Operator notices from the control node go to Hermes, never to macOS notifications.

The operator reads alerts in the Hermes Telegram Inbox topic (2026-10-05: "I want only
hermes"), so every control script sends its notices through here rather than osascript.
Callers keep their own gating (cooldowns, state transitions): each call is one message.

Why ``hermes send`` and not ``hermes-ping``: the operator rule "use hermes-ping, never a
bare hermes send" (2026-10-06) is for agent sessions. hermes-ping's value is naming the
interface, workspace/tab/pane and session the ping came from; a launchd job has none of
those, and hermes-ping lives in the operator's site-djbclark checkout, which this product
repo must not depend on. The title argument says which control job sent the notice.

Destinations come from the site's Telegram inbox register (``site-djbclark/registry/
telegram-inbox.{toml,env}``), never a hard-coded thread id per caller. ``resolve_target``
reads the site's generated ``registry/telegram-inbox.env`` for a given route and falls
back to ``FALLBACK_TARGET`` -- with a logged warning -- when site discovery or that file
is unavailable, so a dead link to the register never silences a monitor. The default
route, "stayturgid.control", is this product's own alert channel (the Watch topic);
individual callers (e.g. check_apk_updates) pass their own route.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from control.lib.site_discovery import (  # noqa: E402
    SiteDiscoveryError,
    SiteSelection,
    reject_private_companion_overlay,
    resolve_site_selection,
)

logger = logging.getLogger(__name__)

# Used only when site discovery or the register's generated env file is
# unavailable. inbox-check (site-djbclark) asserts this equals the
# "stayturgid.control" route's register target, so the fallback can't drift
# silently from the register.
FALLBACK_TARGET = "telegram:838808636:44132"

DEFAULT_ROUTE = "stayturgid.control"

_INBOX_ENV_RELATIVE = Path("registry") / "telegram-inbox.env"


def _resolve_site_dir(environ: Mapping[str, str]) -> Path:
    """Resolve the site overlay directory, mirroring the product's standard precedence.

    Same precedence as ``control/landing/discover.py:_resolve_site``
    (``ANSIBLE_CONFIG`` > ``STAYTURGID_SITE_DIR`` > ``site_discovery``
    fallback chain); duplicated rather than imported because that module
    pulls in discovery/probing machinery this library must not depend on.
    """
    explicit_config = environ.get("ANSIBLE_CONFIG", "").strip()
    explicit_site = environ.get("STAYTURGID_SITE_DIR", "").strip()
    if explicit_config:
        config = Path(explicit_config).expanduser()
        if not config.is_absolute():
            config = (Path.cwd() / config).resolve()
        if not config.is_file():
            raise SiteDiscoveryError(f"ANSIBLE_CONFIG points to a missing file: {config}")
        selection = SiteSelection(path=config.parent.resolve(), source="ANSIBLE_CONFIG")
    elif explicit_site:
        selection = SiteSelection(path=Path(explicit_site).expanduser().resolve(), source="STAYTURGID_SITE_DIR")
    else:
        selection = resolve_site_selection(environ)
    reject_private_companion_overlay(selection.path, environ)
    if not selection.path.is_dir():
        raise SiteDiscoveryError(
            f"Selected site directory does not exist or is not a directory ({selection.source}): {selection.path}"
        )
    return selection.path


def _read_inbox_env(path: Path) -> dict[str, str]:
    """Parse the register's generated ``KEY=value`` env file; {} if unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _route_env_key(route: str) -> str:
    return "INBOX_ROUTE_" + route.upper().replace("-", "_").replace(".", "_")


def resolve_target(
    route: str,
    *,
    environ: Mapping[str, str] | None = None,
    site_dir: Path | None = None,
) -> str:
    """Resolve *route* to a ``telegram:<chat>:<thread>`` target via the inbox register.

    Looks up ``INBOX_ROUTE_<ROUTE>`` in ``<site>/registry/telegram-inbox.env``.
    Falls back to ``FALLBACK_TARGET`` (with a logged warning) when site
    discovery fails, the env file is missing/empty, or the route isn't in it --
    a ping must not be lost over a stale or absent register.
    """
    env = os.environ if environ is None else environ
    if site_dir is None:
        try:
            site_dir = _resolve_site_dir(env)
        except SiteDiscoveryError as exc:
            logger.warning("inbox register: site discovery failed (%s); using fallback target", exc)
            return FALLBACK_TARGET

    env_path = site_dir / _INBOX_ENV_RELATIVE
    values = _read_inbox_env(env_path)
    if not values:
        logger.warning("inbox register: %s missing or empty; using fallback target", env_path)
        return FALLBACK_TARGET

    key = _route_env_key(route)
    target = values.get(key)
    if not target:
        logger.warning("inbox register: route %r not found in %s; using fallback target", route, env_path)
        return FALLBACK_TARGET
    return target


def _hermes_bin() -> str:
    # launchd jobs run with a minimal PATH that may not include ~/.local/bin.
    return shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes")


def notify(title: str, message: str, *, route: str = DEFAULT_ROUTE) -> bool:
    """Send one notice; never raises (a dead transport must not break a monitor).

    Returns True when ``hermes send`` exited 0. Callers that remember what they
    already announced must record it only on True, or a gateway outage loses
    the alert; fire-and-forget callers can ignore the result. *route* selects
    the destination via ``resolve_target``; existing callers that don't pass
    one keep going to this product's own alert channel.
    """
    target = resolve_target(route)
    try:
        result = subprocess.run(
            [_hermes_bin(), "send", "-t", target, "%s: %s" % (title, message)],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
