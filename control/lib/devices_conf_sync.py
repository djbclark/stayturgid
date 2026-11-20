"""Keep the rendered devices.conf complete for the hosts a deploy is about to touch.

devices.conf is rendered from the inventory by the control-node pass (roles/control_node,
templates/devices.conf.j2). A host added to the inventory is therefore missing from it until
that pass has run, and the alias lookups and the USB/LAN heal tools all read this file. The
deploy appends the row the template would render for each missing host, using the same
columns, so onboarding a device needs no hand-edited file. The next control-node pass
re-renders the whole file.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("~/.config/stayturgid/devices.conf")


def conf_path() -> Path:
    return Path(os.environ.get("STAYTURGID_DEVICES_CONF", str(DEFAULT_PATH))).expanduser()


def known_aliases(text: str) -> set[str]:
    aliases: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            aliases.add(stripped.split()[0])
    return aliases


def render_row(host: str, hostvars: dict[str, Any]) -> str:
    """The same columns as devices.conf.j2: alias usb_serial tailscale_ip lan_ip label phone."""
    ip = hostvars.get("ansible_host") or "-"
    lan = hostvars.get("device_lan_ip") or "-"
    return " ".join(
        [
            host,
            str(hostvars.get("device_usb_serial") or "-"),
            str(ip),
            str(lan),
            str(hostvars.get("device_label") or host),
            str(hostvars.get("device_phone_number") or "-"),
        ]
    )


def missing_rows(text: str, inventory: dict[str, Any], hosts: list[str]) -> list[str]:
    hostvars = inventory.get("_meta", {}).get("hostvars", {})
    have = known_aliases(text)
    return [render_row(h, hostvars.get(h, {})) for h in hosts if h not in have and h in hostvars]


def ensure_aliases(inventory: dict[str, Any], hosts: list[str], path: Path | None = None) -> list[str]:
    """Append rows for hosts absent from devices.conf; return the aliases added."""
    path = path or conf_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    rows = missing_rows(text, inventory, hosts)
    if not rows:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (text if text.endswith("\n") or not text else text + "\n") + "\n".join(rows) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return [row.split()[0] for row in rows]
