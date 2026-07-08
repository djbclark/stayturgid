# Shared libraries

Cross-module helpers used by more than one component. **Import these; do not duplicate.**

**Full project:** [../README.md](../README.md)

## Mac / ADB

| File | Purpose |
|------|---------|
| [mac/stayturgid_device.py](mac/stayturgid_device.py) | Device resolution, Shizuku JSON patch, UI XML parsing |
| [mac/adb_cli.py](mac/adb_cli.py) | adb/ssh/scp helpers for Mac CLI scripts |
| [mac/resolve_adb.py](mac/resolve_adb.py) | CLI: USB serial when plugged in, else Tailscale/LAN `:5555` |
| [mac/stayturgid_root.py](mac/stayturgid_root.py) | CLI: find repo root from any nested script path |

### From a Python Mac script

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "mac"))
import adb_cli as adb

serial = adb.resolve_target("s24")
adb.start_autojs_file(serial, "/sdcard/stayturgid/autojs6/main.js")
```

### CLI (shell scripts, Make, ad-hoc)

```bash
./shared/mac/resolve_adb.py s24
./shared/mac/resolve_adb.py --ssh-host s24
ANDROID_SERIAL="$(./shared/mac/resolve_adb.py s24)" fdroidcl install com.example.app
```

## Dependencies

- **stayturgid_device.py / adb_cli.py / resolve_adb.py** — `adb` on PATH; optional SSH config for fleet aliases; `~/.config/stayturgid/devices.conf` from Ansible `mac.yml`.
