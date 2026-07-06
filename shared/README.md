# Shared libraries

Cross-module helpers used by more than one component. **Import these; do not duplicate.**

**Full project:** [../README.md](../README.md)

## Mac / ADB

| File | Purpose |
|------|---------|
| [mac/resolve-adb.sh](mac/resolve-adb.sh) | USB-first serial for `p7a` / `s24` aliases |
| [mac/stayturgid-root.sh](mac/stayturgid-root.sh) | Find repo root from any nested `*/mac/*.sh` |

### From a module script (e.g. `autojs6/mac/deploy.sh`)

```bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$ROOT/shared/mac/resolve-adb.sh"
SERIAL="$(resolve_adb s24)"
```

Or with root discovery:

```bash
# shellcheck source=../../shared/mac/stayturgid-root.sh
source "$(dirname "$0")/../../shared/mac/stayturgid-root.sh"
ROOT="$(stayturgid_root "$0")"
source "$ROOT/shared/mac/resolve-adb.sh"
```

### From `mac/adb-reconnect.sh`

```bash
source "$(dirname "$0")/../shared/mac/resolve-adb.sh"
```

## Dependencies

- **resolve-adb.sh** — only `adb` on PATH; no other stayturgid modules required.
