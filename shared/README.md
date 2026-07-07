# Shared libraries

Cross-module helpers used by more than one component. **Import these; do not duplicate.**

**Full project:** [../README.md](../README.md)

## Mac / ADB

| File | Purpose |
|------|---------|
| [mac/stayturgid_device.py](mac/stayturgid_device.py) | Device resolution, Shizuku JSON patch, UI XML parsing |
| [mac/adb_cli.py](mac/adb_cli.py) | adb/ssh/scp helpers for Mac CLI scripts |
| [mac/resolve-adb.sh](mac/resolve-adb.sh) | Legacy bash `source` helper (prefer `stayturgid_device.resolve_adb`) |
| [mac/stayturgid-root.sh](mac/stayturgid-root.sh) | Find repo root from any nested `*/mac/*.sh` |

### From a Python Mac script

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "mac"))
import adb_cli as adb

serial = adb.resolve_target("s24")
adb.start_autojs_file(serial, "/sdcard/stayturgid/autojs6/main.js")
```

### From a shell script (legacy)

```bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$ROOT/shared/mac/resolve-adb.sh"
SERIAL="$(resolve_adb s24)"
```

## Dependencies

- **stayturgid_device.py / adb_cli.py** — `adb` on PATH; optional SSH config for fleet aliases.
- **resolve-adb.sh** — only `adb` on PATH; no other stayturgid modules required.
