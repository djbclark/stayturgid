# Standalone FIRERPA on unrooted Android

This directory installs the latest FIRERPA/lamda release directly from the upstream
server tarball on an unrooted Android device. It does not require stayturgid, Ansible,
Termux, Magisk, or FIRERPA's APK. The deployment does require a working ADB shell
transport during installation and whenever the server must be started after reboot.

The `justfile` is executable documentation: `just --list` shows its operations,
`just prepare` performs every host-only step, and `just install` performs the full
device deployment. The server and client archives are SHA-256 verified against the
checksums published for the release, and the accessibility patch fails closed for any
release whose driver it has not audited, or whose DEX is not the exact expected bytes.

## What the maintainer's guidance resolved

FIRERPA does not need a separately configurable `authorized_keys` path. SSH trust is
derived from the selected FIRERPA service certificate. On an unrooted device:

- connect as SSH user **`shell`**, not `root`;
- generate a certificate with upstream `tools/cert.py`;
- start the server with the explicit
  `--certificate=/data/local/tmp/firerpa/server/lamda.pem` option;
- use that same `lamda.pem` as the SSH private identity and as the gRPC client
  certificate.

Merely placing `lamda.pem` beside `properties.local` did not select it in the manual
tarball deployment. The explicit launch option matters. PKCS#1-to-PKCS#8 conversion is
not necessary.

For the v10.0 artifact tested on 2026-07-13 (not re-verified for later releases), the
default server authorized-key fingerprint matched the private key embedded by upstream
`tools/ssh.sh`; a separate checked-out `tools/test.pem` did not match. A private custom
certificate avoids any default-key ambiguity and prevents the public upstream default
identity from logging in.

`lamda.pem` contains an unencrypted private key, the leaf certificate, and the root
certificate. Treat it as a secret: keep it mode `0600`, never commit it, and back it up
securely. Anyone holding it can authenticate to both FIRERPA SSH and gRPC.

## Prerequisites

- macOS or Linux host with Bash, Python, `curl`, OpenSSH, [`uv`](https://docs.astral.sh/uv/),
  and Android platform tools. `FIRERPA_PYTHON` defaults to `python3.14`, the newest
  Python the lamda client installs on: lamda declares `Requires-Python <3.15` and
  grpcio publishes no 3.15 wheels. Point `FIRERPA_PYTHON` at another interpreter if
  your host lacks 3.14 or a later lamda release raises that ceiling.
- [`just`](https://github.com/casey/just) 1.20+ (the example is tested with 1.59.0)
- USB debugging or an already-authorized wireless ADB endpoint
- ADB must return Android UID 2000: `adb -s SERIAL shell id -u`
- about 500 MB free on the host and 300 MB under `/data/local/tmp` on the device
- the matching release architecture (`arm64-v8a` for most current phones)

Install the host tools on macOS:

```bash
brew install just android-platform-tools python@3.14 uv
```

On Debian/Ubuntu, install the equivalents and then install `just` using one of the
methods documented by its project:

```bash
sudo apt-get update
sudo apt-get install -y adb curl openssh-client python3 python3-venv
```

Keep port 65000 private. FIRERPA multiplexes gRPC and SSH on that port. Prefer a
Tailscale address, a private LAN, or host firewall rules; do not expose it directly to
the public internet.

## Quick start

From a stayturgid checkout:

```bash
cd examples/firerpa-nonroot
cp .env.example .env
${EDITOR:-vi} .env
just config
just doctor
just install
just ssh-id
just grpc
```

Or copy only this directory elsewhere; it downloads its two lifecycle helpers from
stayturgid `master` (see [Pinning for reproducibility](#pinning-for-reproducibility)):

```bash
mkdir -p ~/firerpa-nonroot
cd ~/firerpa-nonroot
curl -fLO https://raw.githubusercontent.com/djbclark/stayturgid/master/examples/firerpa-nonroot/justfile
curl -fLO https://raw.githubusercontent.com/djbclark/stayturgid/master/examples/firerpa-nonroot/.env.example
curl -fLO https://raw.githubusercontent.com/djbclark/stayturgid/master/examples/firerpa-nonroot/README.md
cp .env.example .env
${EDITOR:-vi} .env
just install
```

`.env` needs two values:

```dotenv
ADB_TARGET=R58M123456A
FIRERPA_HOST=100.0.0.20
```

`ADB_TARGET` may be a USB serial, `host:port`, or another serial accepted by
`adb -s`. `FIRERPA_HOST` is the address SSH and gRPC clients use; it can be a
Tailscale IP or DNS name and does not need to equal `ADB_TARGET`.

Variables can also be supplied without an `.env` file:

```bash
just ADB_TARGET=R58M123456A FIRERPA_HOST=100.0.0.20 install
```

To reuse an existing private certificate, set its absolute path instead of generating
`certs/lamda.pem`:

```bash
FIRERPA_CERTIFICATE=$HOME/.config/firerpa/lamda.pem just grpc
```

For a 32-bit ARM device:

```bash
just ADB_TARGET=SERIAL FIRERPA_HOST=HOST FIRERPA_ARCH=armeabi-v7a install
```

## What `just install` actually does

1. Verifies ADB reaches the expected device as UID 2000 and confirms its ABI.
2. Resolves the latest upstream release (GitHub `releases/latest`) unless
   `FIRERPA_VERSION` is set, and records it in `.work/firerpa-version`.
3. Downloads that release's server and Python-client tarballs, upstream `tools/cert.py`,
   and the stayturgid patch/lifecycle helpers.
4. Verifies the server archive against the release's published `.sha256sum`. The
   release publishes none for the client, so it is verified against the SHA-256 that
   PyPI publishes for the identical `lamda-<version>.tar.gz` sdist. Any pin you set
   (below) replaces those checks.
5. Creates `.work/venv`, installs `cryptography` and the matching lamda client.
6. Runs upstream `cert.py` once in `certs/`, producing `certs/lamda.pem`.
7. Creates the accessibility-compatible `aab.zip` with `--version <release>`.
8. Stops the old FIRERPA process tree, extracts the signed server under
   `/data/local/tmp/firerpa/server`, and saves the signed driver as an override.
9. Pushes the patched driver, lifecycle helper, certificate, and conservative
   `properties.local` (SSH on; built-in ADB, cron, forwarding, mDNS, and WebRTC off).
10. Starts the signed server, waits for FIRERPA's integrity validation, swaps in the
    patched driver atomically, and restarts only FIRERPA's UIAutomation helper processes.
11. Prints the listener, process ownership, and active driver hash.

The patcher keeps an audited entry per release (`SUPPORTED_DRIVERS` in
`firerpa_service_patch.py`). A release without one stops at step 7 with `FIRERPA
<version> has no entry in SUPPORTED_DRIVERS`, before the device is touched, and a
release whose driver bytes changed under an existing entry stops with a SHA-256
mismatch. Neither guesses. Until stayturgid `master` audits the new release, pin
`FIRERPA_VERSION` to the last audited one.

## Pinning for reproducibility

By default every input tracks its latest: the newest FIRERPA release, upstream's
default branch for `tools/cert.py`, and stayturgid `master` for the patch and lifecycle
helpers. Every one of them is an environment variable, so a reproducible deployment
sets fixed values in `.env`:

```dotenv
FIRERPA_VERSION=10.9
STAYTURGID_REF=010ceaf
UPSTREAM_SOURCE_REF=9a4736f327aa89be687ee7c411fee59730081a5e
# Each pin replaces the published-checksum check, or adds one where none exists.
SERVER_SHA256=<sha256 of lamda-server-<arch>.tar.gz>
CLIENT_SHA256=<sha256 of lamda-client-py-<version>.tar.gz>
CERT_TOOL_SHA256=<sha256 of tools/cert.py>
PATCH_SCRIPT_SHA256=<sha256 of firerpa_service_patch.py>
LIFECYCLE_SCRIPT_SHA256=<sha256 of firerpa_lifecycle.py>
```

Use full commit SHAs or short ones you trust; branch names move. To capture the
current values, run `just fetch` once unpinned: it prints the resolved version and an
`unpinned: <sha256>  <file>` line for each helper, and `shasum -a 256 .work/*.tar.gz`
gives the archive hashes. Audit those revisions before you copy them into `.env`.

## Manual commands equivalent to the justfile

These commands are useful for understanding or debugging the automation. Adjust
`SERIAL`, `HOST`, and paths first:

```bash
export SERIAL=R58M123456A
export HOST=100.0.0.20
export PORT=65000
export ROOT=/data/local/tmp/firerpa
export WORK="$PWD/.work"
export CERT="$PWD/certs/lamda.pem"
export PYTHON=python3.14
export VERSION=$(curl -fsSL -o /dev/null -w '%{url_effective}' \
  https://github.com/firerpa/lamda/releases/latest | sed 's|.*/tag/v||')
mkdir -p "$WORK" "$PWD/certs"
chmod 700 "$PWD/certs"
```

Download and verify the upstream arm64 server. Upstream has deleted old
releases before (v10.0 and v10.2 are gone), so a release you pinned may return 404
later.

```bash
curl -fL -o "$WORK/lamda-server-arm64-v8a.tar.gz" \
  "https://github.com/firerpa/lamda/releases/download/v$VERSION/lamda-server-arm64-v8a.tar.gz"
curl -fL -o "$WORK/lamda-server-arm64-v8a.tar.gz.sha256sum" \
  "https://github.com/firerpa/lamda/releases/download/v$VERSION/lamda-server-arm64-v8a.tar.gz.sha256sum"
expected=$(awk 'NR == 1 {print $1}' "$WORK/lamda-server-arm64-v8a.tar.gz.sha256sum")
actual=$($PYTHON -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' \
  "$WORK/lamda-server-arm64-v8a.tar.gz")
test "$actual" = "$expected"
```

Generate the private service certificate with upstream's tool:

```bash
uv venv --python "$PYTHON" "$WORK/venv"
uv pip install --python "$WORK/venv/bin/python" cryptography
curl -fL -o "$PWD/certs/cert.py" \
  https://raw.githubusercontent.com/firerpa/lamda/HEAD/tools/cert.py
(cd "$PWD/certs" && PYTHONWARNINGS=ignore::DeprecationWarning \
  "$WORK/venv/bin/python" cert.py lamda)
chmod 600 "$CERT" "$PWD/certs/root.key"
```

The warning filter is deliberately limited to upstream `cert.py`: its use of naive
`datetime.utcnow()` emits a deprecation warning with current `cryptography`, but does
not change the generated certificate. The justfile suppresses that known warning so
real setup errors remain visible.

Download the patch/lifecycle helpers and build the patched driver. The patcher
takes the release it is patching and refuses one it has not audited:

```bash
base=https://raw.githubusercontent.com/djbclark/stayturgid/master/ansible_collections/stayturgid/firerpa/roles/firerpa/files
curl -fL -o "$WORK/firerpa_service_patch.py" "$base/firerpa_service_patch.py"
curl -fL -o "$WORK/firerpa_lifecycle.py" "$base/firerpa_lifecycle.py"
$PYTHON "$WORK/firerpa_service_patch.py" \
  --version "$VERSION" \
  --archive "$WORK/lamda-server-arm64-v8a.tar.gz" \
  --output "$WORK/aab.zip.patched"
```

Deploy the signed archive and keep both driver variants:

```bash
adb -s "$SERIAL" push "$WORK/lamda-server-arm64-v8a.tar.gz" \
  /data/local/tmp/firerpa-server.tar.gz
adb -s "$SERIAL" shell "
  pkill -9 -x lamda 2>/dev/null || true
  rm -rf '$ROOT/server' /data/local/tmp/usr
  mkdir -p '$ROOT/overrides'
  tar xzf /data/local/tmp/firerpa-server.tar.gz -C '$ROOT'
  cp '$ROOT'/server/lib/python3.*/site-packages/lamda/aab.zip \
     '$ROOT/overrides/aab.zip.signed'
"
adb -s "$SERIAL" push "$WORK/aab.zip.patched" \
  "$ROOT/overrides/aab.zip.patched"
adb -s "$SERIAL" push "$WORK/firerpa_lifecycle.py" \
  "$ROOT/firerpa_lifecycle.py"
adb -s "$SERIAL" push "$CERT" "$ROOT/server/lamda.pem"
adb -s "$SERIAL" shell "chmod 600 '$ROOT/server/lamda.pem'"
```

Create `properties.local` in the extracted `server/` directory. The minimal important
part is:

```ini
port = 65000
[sshd]
sshd.enable = true

[adb]
adb.enable = false
```

For example:

```bash
printf '%s\n' \
  'port=65000' \
  '[sshd]' 'sshd.enable=true' \
  '[adb]' 'adb.enable=false' > "$WORK/properties.local"
adb -s "$SERIAL" push "$WORK/properties.local" "$ROOT/server/properties.local"
```

Then start through the lifecycle controller. Do not replace the signed active driver with
the patch before startup: FIRERPA validates its signed driver during initialization.

```bash
$PYTHON "$WORK/firerpa_lifecycle.py" start \
  --adb-target "$SERIAL" \
  --root "$ROOT" \
  --port "$PORT" \
  --certificate "$ROOT/server/lamda.pem"
```

Test SSH as `shell` with the same certificate file:

```bash
ssh -o IdentitiesOnly=yes -i "$CERT" -p "$PORT" "shell@$HOST" id
# Expected: uid=2000(shell) ...
```

Install and test the gRPC client (the release publishes no checksum for it; PyPI's
`https://pypi.org/pypi/lamda/$VERSION/json` lists the SHA-256 of the identical
`lamda-$VERSION.tar.gz`):

```bash
curl -fL -o "$WORK/lamda-client-py-$VERSION.tar.gz" \
  "https://github.com/firerpa/lamda/releases/download/v$VERSION/lamda-client-py-$VERSION.tar.gz"
uv pip install --python "$WORK/venv/bin/python" "$WORK/lamda-client-py-$VERSION.tar.gz"
"$WORK/venv/bin/python" - "$HOST" "$PORT" "$CERT" <<'PY'
from lamda.client import Device
import sys

d = Device(sys.argv[1], port=int(sys.argv[2]), certificate=sys.argv[3])
info = d.server_info()
print(f"FIRERPA v{info.version} uptime={info.uptime}s")
PY
```

## Why the accessibility driver lifecycle exists

FIRERPA bundles an `Instrumentation` subclass whose no-argument `getUiAutomation()`
override connects with flags `0`. Android then suppresses normal accessibility services,
which disconnects automation tools such as AutoJs6, AutoInput, or screen readers.
Android exposes `FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES` (value `1`) to preserve them.

The patch rewrites that override's 12-byte prologue, hash-pinned per release, so it
delegates to the flag-aware `getUiAutomation(1)` overload, then repairs the DEX
signature/checksum. That single chokepoint covers every call site. FIRERPA also
validates the signed `aab.zip` at startup, so leaving the patched archive active before
launch fails integrity validation.
The lifecycle controller therefore:

1. restores the signed original;
2. starts FIRERPA and waits for its listener and original helper;
3. atomically activates the patched driver;
4. kills only the original UI helper;
5. waits for FIRERPA to respawn it from the patched driver.

If no other accessibility services matter on your device, you can run the signed
server directly. The lifecycle approach is safer when coexistence matters.

## Reboot and Shizuku tips

The tarball is not an Android app and has no boot receiver. It must be started as Android
UID 2000 after reboot. USB ADB, authorized wireless ADB, or a persistent localhost ADB
bridge can do that.

A FIRERPA child launched directly in a Shizuku `rish` command dies when its binder shell
session closes, even with `nohup` or `setsid`. A working pattern is to use `rish` only to
restore persistent adbd, then launch FIRERPA through ADB:

```bash
# Run from an authorized Termux/Shizuku environment:
rish -c 'setprop service.adb.tcp.port 5555; setprop ctl.restart adbd'
adb connect localhost:5555
adb -s localhost:5555 shell id -u  # must print 2000
# The lifecycle helper itself is stdlib-only; use Termux's available python3.
python3 firerpa_lifecycle.py start \
  --adb-target localhost:5555 \
  --root /data/local/tmp/firerpa \
  --port 65000 \
  --certificate /data/local/tmp/firerpa/server/lamda.pem
```

Grant the calling app persistent Shizuku authorization if the device offers it. If both
ADB and Shizuku are down after reboot, an unrooted app process cannot manufacture UID 2000;
restore USB/wireless debugging first.

## Troubleshooting

### `Permission denied (publickey)`

- Verify the username is `shell`, not `root`.
- Add `-o IdentitiesOnly=yes` so an SSH agent does not offer unrelated keys first.
- Verify the server was started with the explicit `--certificate=.../lamda.pem` option.
- Verify the client uses the same `lamda.pem` that was pushed to the server.
- Inspect a key fingerprint with `ssh-keygen -yf certs/lamda.pem | ssh-keygen -lf -`.

### gRPC TLS or certificate failure

Pass the same local `lamda.pem` as `Device(..., certificate=...)`. An unauthenticated
client should be rejected after custom certificate deployment; that is expected.

### Accessibility services disappear

The original flags-0 UIAutomation helper is active. Run `just start`; the idempotent
lifecycle controller will restore the patched helper. `just status` compares the active
`aab.zip` with the SHA-256 of the `.work/aab.zip.patched` that `just patch` built.

### FIRERPA reports an integrity error

The patched archive was active too early. Restore
`overrides/aab.zip.signed` to the active `lamda/aab.zip`, start the server, and
let the lifecycle controller perform the swap after validation.

### `has no entry in SUPPORTED_DRIVERS` or `does not match SUPPORTED_DRIVERS`

Do not bypass it. The release's driver has not been audited for this patch. Pin
`FIRERPA_VERSION` to the last audited release (the error lists them), or wait for
stayturgid `master` to add an entry for the new one.

### Server launched through `rish` vanishes immediately

This is binder-session lifetime, not a certificate problem. Restore persistent adbd with
`rish`, then launch via ADB as shown above.

## Updating, stopping, and removing

```bash
just stop                         # keep files and certificate
just start                        # idempotent restart
just clean                        # remove host downloads; preserve certs/
just CONFIRM=YES uninstall        # remove device files; preserve host certs/
```

Never delete the only copy of `certs/lamda.pem` during an upgrade. Existing clients and
SSH identities depend on it. Run `just prepare` before a device upgrade; it fails
before the device is touched if the new release has no audited patch.

## Relevant stayturgid implementation files

- [Version-keyed DEX/driver patcher](https://github.com/djbclark/stayturgid/blob/master/ansible_collections/stayturgid/firerpa/roles/firerpa/files/firerpa_service_patch.py)
- [Signed-start/patched-swap lifecycle controller](https://github.com/djbclark/stayturgid/blob/master/ansible_collections/stayturgid/firerpa/roles/firerpa/files/firerpa_lifecycle.py)
- [Ansible install tasks](https://github.com/djbclark/stayturgid/blob/master/ansible_collections/stayturgid/firerpa/roles/firerpa/tasks/install.yml)
- [Certificate and properties configuration](https://github.com/djbclark/stayturgid/blob/master/ansible_collections/stayturgid/firerpa/roles/firerpa/tasks/configure.yml)
- [Secure client certificate resolution](https://github.com/djbclark/stayturgid/blob/master/control/lib/firerpa_auth.py)
- [Investigation handoff and verification record](https://github.com/djbclark/stayturgid/blob/master/docs/operations/deep-dives/firerpa-ssh-investigation.md)
