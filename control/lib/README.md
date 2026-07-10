# Shared libraries

Cross-module helpers used by more than one component. **Import these; do not duplicate.**

**Full project:** [../../README.md](../../README.md)

## Mac / ADB

| File | Purpose |
|------|---------|
| [stayturgid_device.py](stayturgid_device.py) | Device resolution, Shizuku JSON patch, UI XML parsing |
| [adb_cli.py](adb_cli.py) | adb/ssh/scp helpers for Mac CLI scripts |
| [resolve_adb.py](resolve_adb.py) | CLI: USB serial when plugged in, else Tailscale/LAN `:5555` |
| [stayturgid_root.py](stayturgid_root.py) | CLI: find repo root from any nested script path |

### From a Python Mac script

```python
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]  # control/tools/<domain>/script.py
sys.path.insert(0, str(REPO / "control" / "lib"))
import adb_cli as adb

serial = adb.resolve_target("s24")
adb.start_autojs_file(serial, "/sdcard/stayturgid/autojs6/main.js")
```

### CLI (shell scripts, Make, ad-hoc)

```bash
./control/lib/resolve_adb.py s24
./control/lib/resolve_adb.py --ssh-host s24
ANDROID_SERIAL="$(./control/lib/resolve_adb.py s24)" fdroidcl install com.example.app
```

## Dependencies

- **stayturgid_device.py / adb_cli.py / resolve_adb.py** — `adb` on PATH; optional SSH config for fleet aliases; `~/.config/stayturgid/devices.conf` from Ansible `control_node` role.
