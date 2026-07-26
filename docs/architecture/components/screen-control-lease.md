# Device Screen Control Lease (DSCL v1)

Cross-project standard so multiple agents on the same Mac (e.g. **stayturgid**
and another remote-control project) do not fight over the same phone screen.

## Why

`stock-android-device` (and any fleet host) may be driven by more than one codebase. Without a
shared lease:

- Two agents invert the display / tap at once
- Consent dialogs race
- UI state is corrupted mid-flow

## Where leases live (vendor-neutral)

```text
~/.local/state/device-screen-control/leases/<device_key>.json
```

| Env                              | Purpose                                                        |
| -------------------------------- | -------------------------------------------------------------- |
| `DEVICE_SCREEN_CONTROL_DIR`      | Override root (default `~/.local/state/device-screen-control`) |
| `DEVICE_SCREEN_CONTROL_PROJECT`  | Project id (stayturgid sets `stayturgid`)                      |
| `DEVICE_SCREEN_CONTROL_AGENT`    | Agent name (fallback `STAYTURGID_AGENT`)                       |
| `DEVICE_SCREEN_CONTROL_FORCE=1`  | Steal lease (emergency only)                                   |
| `DEVICE_SCREEN_CONTROL_WAIT_SEC` | Wait for foreign lease to expire before failing                |

XDG: if `XDG_STATE_HOME` is set, root is `$XDG_STATE_HOME/device-screen-control`.

## Schema (`device-screen-control-lease/v1`)

```json
{
  "schema": "device-screen-control-lease/v1",
  "device": "stock-android-device",
  "device_ids": [
    "stock-android-device",
    "EXAMPLE-SERIAL-STOCK",
    "100.0.0.12:5555"
  ],
  "holder": {
    "project": "other-project-name",
    "agent": "claude",
    "session_id": "uuid",
    "pid": 12345,
    "hostname": "macbook"
  },
  "purpose": "ui automation batch",
  "started_at": "2026-07-10T12:00:00Z",
  "heartbeat_at": "2026-07-10T12:05:00Z",
  "expires_at": "2026-07-10T12:30:00Z",
  "ttl_sec": 1800
}
```

**Rules**

1. **Before** any `adb input` / UI automation on a device, `check` for an active lease.
2. If held by **another** `holder.project` → **do not take the glass** (exit / wait).
3. On start of control: **acquire** (write lease, heartbeat while holding).
4. On end: **release** (delete only if you own the lease).
5. Heartbeat at least every ~60s while active; hard stop is `expires_at`.
6. **Renew** only when free, same `session_id`, same process `pid`, or
   `DEVICE_SCREEN_CONTROL_FORCE=1`. Same project with a _different_ session must
   wait or force (no silent peer takeover). Acquire/heartbeat/release use an
   exclusive flock; multi-key leases refresh every `device_ids` alias on heartbeat.

## stayturgid integration

| Piece                                | Role                                                            |
| ------------------------------------ | --------------------------------------------------------------- |
| `control/lib/device_screen_lease.py` | DSCL library                                                    |
| `control/bin/screen_lease.py`        | CLI status/check/acquire/release                                |
| `control/lib/screen_control.py`      | `ScreenControlSession` acquires Mac lease before consent        |
| On-device mirror                     | `/sdcard/stayturgid/state/screen_control_lease.json` (presence) |

```bash
python3 control/bin/screen_lease.py status
python3 control/bin/screen_lease.py check stock-android-device    # exit 1 if foreign hold
python3 control/bin/screen_lease.py acquire stock-android-device --purpose "manual test"
python3 control/bin/screen_lease.py release stock-android-device
```

Agents: at session start, after `just health`, also:

```bash
python3 control/bin/screen_lease.py status
```

If `stock-android-device: HELD project=…` for a **non-stayturgid** project, tell the operator and
prefer **oneui-device** / skip stock-android-device UI until free.

### RevengeQuickSwitcher (reference interop)

Sibling project on the same Mac — implements DSCL v1 without forking the library:

| Setting                         | Value                                                       |
| ------------------------------- | ----------------------------------------------------------- |
| `DEVICE_SCREEN_CONTROL_PROJECT` | `RevengeQuickSwitcher`                                      |
| `STAYTURGID_SCREEN_PURPOSE`     | `qss-qa`                                                    |
| Lease preflight                 | `scripts/device_qa_qss.py` → `preflight_screen_lease()`     |
| Session acquire                 | `ScreenControlSession` from `control/lib/screen_control.py` |
| Operator check                  | `make lease-status` in RevengeQuickSwitcher repo            |

QSS imports `device_screen_lease` from `stayturgid/control/lib` via `STAYTURGID_REPO`.
Foreign holds surface as `screen_lease_foreign_hold` in QA `report.json`.

## On-device path (optional mirror)

stayturgid still writes
`/sdcard/stayturgid/state/screen_control_lease.json` for inversion/guard.
Other projects **must** implement the **Mac** store above for interop; they may
optionally mirror on-device if they use the same path.

---

## Interop prompt (give this to another AI / project)

Copy everything below the line into the other project’s agent:

---

### Prompt: implement Device Screen Control Lease (DSCL v1) interop

You share Android devices with another project (**stayturgid**) on the same Mac.
Both must honor **DSCL v1** so only one project drives a phone’s screen at a time.

**Lease directory (create if missing):**

```text
~/.local/state/device-screen-control/leases/
```

(or `$DEVICE_SCREEN_CONTROL_DIR/leases/` if set; or `$XDG_STATE_HOME/device-screen-control/leases/`)

**File:** one JSON file per device key, e.g. `stock-android-device.json`, `oneui-device.json`, or a
normalized serial. Filename = lowercase alias/serial with non-alnum → `_`.

**JSON schema** — write/read exactly this shape:

```json
{
  "schema": "device-screen-control-lease/v1",
  "device": "<primary-alias-or-serial>",
  "device_ids": ["<alias>", "<usb-serial>", "<ip:5555>", "..."],
  "holder": {
    "project": "<YOUR_PROJECT_SLUG>",
    "agent": "<claude|codex|human|...>",
    "session_id": "<uuid>",
    "pid": 0,
    "hostname": "<hostname>"
  },
  "purpose": "<short reason>",
  "started_at": "<ISO-8601 UTC with Z>",
  "heartbeat_at": "<ISO-8601 UTC with Z>",
  "expires_at": "<ISO-8601 UTC with Z>",
  "ttl_sec": 1800
}
```

**Protocol (mandatory before any adb `input` / UI automation):**

1. **check** — scan all `leases/*.json`. A lease is **active** if `expires_at` > now.
   Match if any of your device identifiers appear in `device` or `device_ids`
   (case-insensitive).
2. If active and held by another controller → **abort UI work** (or wait up to
   `DEVICE_SCREEN_CONTROL_WAIT_SEC`). That includes **same project, different
   session** (peer agent) as well as a foreign `holder.project`. Print holder
   project/agent/purpose/expiry.
3. If free, same session, or same process pid → **acquire**: write/update JSON
   under every device key/alias with your project, `session_id`,
   `expires_at = now + ttl`. Do not silent-takeover a peer session without FORCE.
4. While controlling: **heartbeat** every ≤60s (refresh `heartbeat_at` + `expires_at`
   on **all** alias files for that lease).
5. When done: **release** — delete the lease file **only if** `holder.project` is yours
   (and preferably same `session_id`). Never delete another project’s lease unless
   `DEVICE_SCREEN_CONTROL_FORCE=1` and the operator confirmed.
6. Announce to the human: `USING — <device>` when you acquire, `FREE — <device>` when you release.

**Env vars your project should honor:**

| Var                              | Meaning                                 |
| -------------------------------- | --------------------------------------- |
| `DEVICE_SCREEN_CONTROL_DIR`      | Override store root                     |
| `DEVICE_SCREEN_CONTROL_PROJECT`  | Your project slug (required uniqueness) |
| `DEVICE_SCREEN_CONTROL_AGENT`    | Agent display name                      |
| `DEVICE_SCREEN_CONTROL_FORCE`    | Steal lease (dangerous; operator-only)  |
| `DEVICE_SCREEN_CONTROL_WAIT_SEC` | Seconds to wait for foreign lease       |

**Do not** use stayturgid-only paths as the sole signal. Mac DSCL is the interop
surface. Optional: also read/write
`/sdcard/stayturgid/state/screen_control_lease.json` if you already SSH to
Termux, but Mac leases are authoritative for multi-project arbitration.

**Minimal Python sketch:**

```python
# Before UI work:
from pathlib import Path
import json, time, os, uuid, socket

override = os.environ.get("DEVICE_SCREEN_CONTROL_DIR", "").strip()
xdg = os.environ.get("XDG_STATE_HOME", "").strip()
ROOT = (
    Path(override)
    if override
    else Path(xdg).expanduser() / "device-screen-control"
    if xdg
    else Path.home() / ".local" / "state" / "device-screen-control"
).expanduser()
LEASES = ROOT / "leases"
PROJECT = os.environ.get("DEVICE_SCREEN_CONTROL_PROJECT", "my-project")


def active_foreign(device_ids):
    LEASES.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for p in LEASES.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        # parse expires_at ISO Z → epoch; skip if expired
        ...
        ids = {d.get("device"), *(d.get("device_ids") or [])}
        if ids & set(device_ids) and d.get("holder", {}).get("project") != PROJECT:
            return d
    return None
```

Implement check/acquire/heartbeat/release in your project’s screen-control entry
point and call them on every UI session. Interop with stayturgid is complete when
both write the same directory and refuse foreign active leases.

---

## Related

- [docs/architecture/components/control.md](control.md) — Mac tools
- [control/lib/screen_control.py](../../../control/lib/screen_control.py) — session wrapper
- Handoff phone protocol: USING / FREE announcements

## Consent / presence vs lease (related)

Mac `ScreenControlSession` order: **DSCL lease → consent/request-screen → inversion → presence on**.

- **Lease** is multi-project arbitration (this document).
- **`request-screen`** may fail-open on timeout depending on caller (soft UX).
- **`gate` / consent** and **presence on** are fail-closed — see [termux.md](termux.md).

Do not treat a free lease as “consent granted.”

## Portrait lock (related)

While a screen-control session is held, stayturgid also applies a **natural-portrait**
rotation preference (`user_rotation=0`, accelerometer rotation off) so multi-step UI
automation does not flip landscape mid-batch. Restored when the session ends. See
`control/lib/screen_control.py` (`apply_portrait_lock`) and the on-device twin in
`device/termux/py/stayturgid_screen_control.py`.
