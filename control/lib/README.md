# Shared libraries

Cross-module helpers used by more than one component. **Import these; do not duplicate.**

**Full project:** [../../README.md](../../README.md)

## Mac / ADB

| File                                         | Purpose                                                     |
| -------------------------------------------- | ----------------------------------------------------------- |
| [stayturgid_device.py](stayturgid_device.py) | Device resolution, Shizuku JSON patch, UI XML parsing       |
| [adb_cli.py](adb_cli.py)                     | adb/ssh/scp helpers for Mac CLI scripts                     |
| [resolve_adb.py](resolve_adb.py)             | CLI: USB serial when plugged in, else Tailscale/LAN `:5555` |
| [stayturgid_root.py](stayturgid_root.py)     | CLI: find repo root from any nested script path             |

### From a Python Mac script

```python
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]  # control/tools/<domain>/script.py
sys.path.insert(0, str(REPO / "control" / "lib"))
import adb_cli as adb

serial = adb.resolve_target("oneui-device")
adb.start_autojs_file(serial, "/sdcard/stayturgid/autojs6/main.js")
```

### CLI (shell scripts, Make, ad-hoc)

```bash
./control/lib/resolve_adb.py oneui-device
./control/lib/resolve_adb.py --ssh-host oneui-device
ANDROID_SERIAL="$(./control/lib/resolve_adb.py oneui-device)" fdroidcl install com.example.app
```

## Dependencies

- **stayturgid_device.py / adb_cli.py / resolve_adb.py** — `adb` on PATH; optional SSH config for fleet aliases; `~/.config/stayturgid/devices.conf` from Ansible `control_node` role.

## Additional libraries (index)

| Module                                             | Role                                                          |
| -------------------------------------------------- | ------------------------------------------------------------- |
| `et_mac.py`                                        | Phone→Mac Eternal Terminal authorized_keys / soft checks      |
| `ssh_marked_block.py`                              | Marked blocks in authorized_keys / ssh config                 |
| `screen_control.py`                                | Mac ScreenControlSession (inversion, presence, portrait lock) |
| `device_screen_lease.py`                           | Cross-project glass lease (DSCL v1)                           |
| `fleet_health.py`                                  | Soft-health scrape + issue tags for monitors                  |
| `ui_driver.py` / `ui_clearance.py` / `ui_parse.py` | UI automation helpers                                         |
| `hd8_google_stack.py`                              | Fire HD8 Play/GMS stack helpers                               |
| `post_ui_remote.py`                                | Post-deploy UI remote steps                                   |
| `a11y_services.py`                                 | Accessibility service merge/profiles                          |
| `termux_api.py` / `termux_ssh_bootstrap.py`        | Termux API + SSH bootstrap                                    |
| `play_store_autoupdate.py`                         | Play auto-update checks                                       |
| `stayturgid_root.py`                               | Repo-root discovery                                           |
| `*.json` profiles                                  | a11y / fleet app / AutoJs6 drawer defaults                    |

See [docs/architecture/components/control.md](../../docs/architecture/components/control.md), and [docs/architecture/components/screen-control-lease.md](../../docs/architecture/components/screen-control-lease.md).
