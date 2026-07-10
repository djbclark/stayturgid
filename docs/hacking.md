# HACKING — stayturgid Development Environment

This document gets a developer from a clean Android + macOS install to a fully working development environment for stayturgid. Follow the sections in order — Android setup first, then Mac, then verification.

---

## What you're setting up

| Layer | Role |
|-------|------|
| Android device | Runs AutoJs6, Shizuku, Termux — the managed stack |
| macOS (Mac) | Development workstation; runs ADB, Ansible, AI coding agent |
| AutoJs6 | Watchdog automation on the device (accessibility + Termux bridge) |
| Shizuku (thedjchi fork) | Shell-privileged adbd on port 5555 via Wireless Debugging (no root) |
| Termux | Linux environment on Android — runs sshd, adb, the boot script |

---

## Tested versions

### Android device
| App | Package | Version | Source |
|-----|---------|---------|--------|
| Android | — | 16 (SDK 36) | — |
| AutoJs6 | `org.autojs.autojs6` | 6.7.0 | GitHub (see below) |
| Shizuku (thedjchi fork) | `moe.shizuku.privileged.api` | 13.6.0.r1349-thedjchi-beta | GitHub (see below) |
| Termux | `com.termux` | 2026.06.21 | Google Play or F-Droid |
| Termux:Boot | `com.termux.boot` | 0.8.1 | F-Droid / GitHub |
| Termux:API (app) | `com.termux.api` | 0.53.0 | F-Droid / GitHub |

### Termux packages (installed inside Termux via `pkg`)
| Package | Version |
|---------|---------|
| openssh | 10.3p1-1 |
| termux-api (CLI) | 0.59.1 |
| android-tools (adb) | 35.0.2-7 |
| python | 3.13.13-1 |
| curl | 8.21.0 |
| wget | 1.25.0-1 |

### macOS development tools
| Tool | Version | Install |
|------|---------|---------|
| macOS | Sequoia 15.x+ | — |
| Homebrew | current | https://brew.sh |
| ADB (platform-tools) | 1.0.41 / 37.0.0-14910828 | `brew install android-platform-tools` |
| Python | 3.14.6 | `brew install python` |
| pipx | 1.15.0 | `brew install pipx` |
| Handsets (`~/.handsets/hs`) | 0.1.x | Mac primary UI driver — see `control/lib/ui_driver.py` |
| uiautomator2 (Python) | 3.7.0 | Optional Mac debug only (`pipx install uiautomator2`) |
| Claude Code (AI agent) | current | `npm install -g @anthropic-ai/claude-code` |
| git | current | `brew install git` |

---

## Part 1 — Android setup

### 1.1 Enable Developer Options and Wireless Debugging

1. **Settings → About phone → Build number**: tap 7 times to enable Developer Options.
2. **Settings → System → Developer options**:
   - Enable **USB debugging**
   - Enable **Wireless debugging**
3. Open **Wireless debugging** and note the IP address and port shown (you'll need this for pairing, but ADB on the Mac will handle it automatically once you connect via USB).

### 1.2 Install Android apps

Install the following apps.

#### Shizuku — thedjchi fork (CRITICAL: must be this fork)

The standard Shizuku from Play Store **does not have TCP mode**. You need thedjchi's fork which adds automatic boot-time TCP (port 5555) support via Wireless Debugging.

**Source:** https://github.com/thedjchi/Shizuku/releases

**Obtainium URL** (add this in Obtainium → Add App):
```
https://github.com/thedjchi/Shizuku
```
Select: "GitHub Releases" → filter for `.apk`.

Install the latest `app-release.apk` from the releases page. Current version: **13.6.0.r1349-thedjchi-beta**.

#### Termux (install from F-Droid or Google Play)

```
https://github.com/termux/termux-app
```
Or F-Droid: search "Termux" by Termux Dev Team.

> Note: F-Droid and Google Play builds are signed differently and **cannot coexist**. Pick one source and stick with it. Google Play version may lag behind F-Droid.

#### Termux:Boot

```
https://github.com/termux/termux-boot
```
Or F-Droid: search "Termux:Boot".

**Must match the signing source of Termux** (F-Droid with F-Droid, Play with Play).

#### Termux:API (app)

```
https://github.com/termux/termux-api
```
Or F-Droid: search "Termux:API".

#### AutoJs6 (stayturgid watchdog)

JavaScript automation engine — runs the stayturgid watchdog (accessibility UI repair + Termux bridge). See [docs/modules/autojs6.md](modules/autojs6.md).

**Source:** https://github.com/SuperMonster003/AutoJs6/releases

**Obtainium URL** (add this in Obtainium → Add App, or import `catalogs/obtainium/autojs6-only.json` via `control/tools/obtainium/sync_to_device.py`):
```
https://github.com/SuperMonster003/AutoJs6
```
APK filter: `arm64-v8a` (or enable auto-filter-by-arch). Grant **Run commands in Termux environment** after install.

#### Tailscale

Gives the device a stable `100.x.y.z` IP that survives DHCP lease changes and network switches — so `adb connect <tailscale-ip>:5555` and SSH keep working without hunting for the current WiFi IP. (The S24's LAN IP changed mid-session once and broke every hardcoded `adb connect`; Tailscale eliminates that failure mode.)

**Obtainium URL** (add this in Obtainium → Add App):
```
https://github.com/tailscale/tailscale-android
```
Select: "GitHub Releases" → filter for `.apk`.

After install: sign in, and in Tailscale settings consider enabling **VPN On-Demand / Always-on VPN** so the tunnel survives reboots.

#### Obtainium — quieter installs via Shizuku

After Shizuku is running and Obtainium is in the manager's authorized-app list:

```bash
chmod +x control/tools/obtainium/enable_shizuku_installer.py
./control/tools/obtainium/enable_shizuku_installer.py s24   # phone unlocked
```

This grants `moe.shizuku.manager.permission.API_V23`, merges Obtainium into `/data/local/tmp/shizuku/shizuku.json`, and toggles **Use Dhizuku, Shizuku or Sui to install** in Obtainium settings (approves the Shizuku permission dialog if shown). Bulk updates: `./control/tools/obtainium/apply_updates.py s24`.

---

### 1.3 Configure Shizuku (thedjchi fork)

Open Shizuku → **Settings (gear icon)**. Set:

| Setting | Value | Why |
|---------|-------|-----|
| Start on boot | ON | Auto-starts via Wireless Debugging on every reboot |
| Watchdog (restart if crash) | ON | Auto-restarts Shizuku if it crashes |
| TCP mode | ON | Calls `adb tcpip 5555` after starting — this opens port 5555 without USB |
| TCP port | 5555 (default) | Standard wireless ADB port |
| Auto-disable USB debugging | OFF | Leave USB debugging active |

Then tap **Start via Wireless debugging → Start**. Once it's running you should see the Shizuku notification. Subsequent reboots are automatic.

---

### 1.4 Configure Termux

**Package policy:** at the start of any Termux setup or maintenance session, refresh the package index and upgrade everything already installed. Before installing any new package, run `pkg update && pkg upgrade -y` again (even if you just ran it).

Open Termux and install the required packages:

```bash
pkg update && pkg upgrade -y
pkg update && pkg upgrade -y && pkg install openssh android-tools termux-api python wget curl -y
```

**Set up the SSH server and your public key:**

```bash
# Generate a key on the Mac first (if you don't have one):
# ssh-keygen -t ed25519 -f ~/.ssh/termux_key

# One-time bootstrap (when Ansible cannot SSH yet):
./control/bin/bootstrap_ssh.py s24
# Or: adb push + run-as com.termux (automated by bootstrap_ssh.py on debug Termux)
# Manual fallback:
# ssh-copy-id -i ~/.ssh/termux_key.pub -p 8022 USER@DEVICE_IP
# Or manually on device:
# mkdir -p ~/.ssh && chmod 700 ~/.ssh
# echo "YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
```

After bootstrap, `ansible/playbooks/site.yml` (via `make deploy` / `deploy_fleet.py`)
keeps fleet SSH keys in sync. **`./control/bin/bootstrap_ssh.py`** (also auto-run from
`control/bin/deploy_termux.py` via `fleet/bootstrap.yml` when SSH fails) installs
control-node `*.pub` keys via adb + `run-as com.termux`, starts `sshd`, and
verifies over USB forward (`adb forward tcp:8022 tcp:8022`) or Tailscale SSH
alias. Live fleet deploy uses **`preflight.yml`** (start of `site.yml`) for
conditional bootstrap instead of the full `bootstrap` tag.

- **Public keys:** every `*.pub` under `stayturgid_ssh_keys_dir` (default
  `~/.ssh` on the Mac) is installed on every device via
  `ansible.posix.authorized_key`.
- **Device mesh:** each device gets a per-host `id_ed25519_fleet` keypair; every
  fleet member's pubkey is installed on every other device via
  `ansible.posix.authorized_key`. Every device also gets every peer's sshd host
  key in `~/.ssh/known_hosts` via `ansible.builtin.known_hosts` (aliases:
  inventory name, Tailscale IP, LAN IP).
- **Private keys:** matching `id_*` (without `.pub`) and `termux_key` are copied
  from the Mac to each device's `~/.ssh/`. Keys are never committed to git.
- **Mac client:** `ansible/playbooks/control_node/agents.yml` renders `~/.ssh/config.d/stayturgid`
  and trusts each fleet host's sshd key in `~/.ssh/known_hosts`.

Override discovery with `stayturgid_ssh_public_key_files` or
`stayturgid_ssh_keys_dir` in inventory `group_vars`. Disable mesh pieces with
`stayturgid_ssh_mesh_device_identity` / `stayturgid_ssh_mesh_known_hosts`.

**Start sshd and test it (from Mac):**

```bash
# On device in Termux:
sshd

# On Mac (device connected via USB):
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost
```

**Deploy the Termux:Boot script:**

```bash
# From Mac (with repo cloned to ~/stayturgid/):
adb push ~/stayturgid/device/termux/boot/start-adb.sh /sdcard/start-adb.sh

# In Termux on device:
mkdir -p ~/.termux/boot
cp /sdcard/start-adb.sh ~/.termux/boot/start-adb.sh
chmod +x ~/.termux/boot/start-adb.sh
```

Open the **Termux:Boot app** once to register its `BOOT_COMPLETED` receiver — it won't fire on boot until you do this.

**Verify Termux:API is working:**

```bash
# In Termux (or via SSH):
termux-battery-status
# Should return JSON like: {"health":"GOOD","percentage":85,...}
```

If the command hangs or errors, make sure the Termux:API app is installed (section 1.2) and that you've granted it the necessary permissions when prompted.

---

### 1.5 Install and configure the AutoJs6 watchdog

All of this is scripted from the Mac (device connected via USB or wireless ADB):

```bash
./control/tools/autojs6/setup_autojs6.py p7a     # install/verify AutoJs6, grant permissions, deploy project
./control/tools/autojs6/set_automation_mode.py p7a
./control/tools/autojs6/start_watchdog.py p7a
```

On-device setup is automated: `enable_autojs6_shizuku.py` enables the accessibility service and Shizuku drawer; `setup_autojs6.py` / fleet harden grant storage, `RUN_COMMAND`, and battery settings. Termux `allow-external-apps=true` is set by the Ansible deploy (or manually in `~/.termux/termux.properties`).

See [docs/modules/autojs6.md](modules/autojs6.md) for details.

---

## Part 2 — macOS setup

### 2.1 Install Homebrew and core tools

Homebrew itself and project formulae are installed by Ansible (`control_node/prereqs.yml`) on
`make deploy-mac` or `make deploy`:

```bash
make deploy-mac          # Homebrew bootstrap (if missing) + adb, python, pipx, git, ansible, scrcpy
pipx ensurepath          # once, if pipx was just installed
```

The playbook runs the standard Homebrew install script when `brew` is not on PATH, then
uses `community.general.homebrew` for formulae. When app stores are re-enabled
(`stayturgid_app_stores_enabled: true`), `fdroidcl` and `apkeep` are included too.
`uiautomator2` is installed via `community.general.pipx`.

Still manual: Handsets, SSH key generation (`termux_key`, `adbkey`), `play.env`,
Claude Code, Node.

### 2.2 Install Handsets (primary Mac UI driver)

Fleet Mac post-UI uses Handsets via `control/lib/ui_driver.py` (not stock
`hs use` with `ip:5555`). Install into `~/.handsets/{hs,hs.jar}` and invoke
as `~/.handsets/hs` (PATH `hs` may be a herdr alias — do not overwrite).

Ports: s24 **9009**, hd8 **9008**, p7a **9010**. Do **not** run alongside
uiautomator2. Research + bench: `docs/research/ui-automation.md`,
`docs/research/handsets-vs-u2-bench.md`,
`docs/research/handsets-under-termux.md`.

**Fire OS (hd8):** Termux cannot `adb connect localhost:5555`. On-device
Handsets starts via **peer bootstrap** — hd8 SSHs to s24/p7a, which run
`stayturgid_peer_help.py` over ADB. See
`docs/research/fire-os-local-adb.md`.

**Shared fleet ADB key** (one Allow covers every phone helper):

```bash
mkdir -p ~/.config/stayturgid
adb keygen ~/.config/stayturgid/adbkey   # once on the Mac; never commit
```

Ansible deploys that keypair to each device as `~/.stayturgid/adbkey-fleet`
(does **not** overwrite `~/.android/adbkey`, which stays device-native for
localhost:5555). First helper connect to a Fire still needs one
**Always allow** tap on the target.

**rish** installs by default into `~/.stayturgid/bin/rish` (from the Shizuku
APK). Useful on stock Android; on Fire the Termux↔Shizuku binder often times
out — peer ADB is the Handsets starter there.

### 2.3 Install uiautomator2 (optional Mac debug)

uiautomator2 is optional for one-off Mac debugging. Prefer Handsets for fleet
scripts. Never run u2 while a Handsets daemon holds UiAutomation.

Installed by Ansible (`community.general.pipx`) on `make deploy-mac`. Manual:

```bash
pipx install uiautomator2
```

Verify:
```bash
/Users/$(whoami)/.local/bin/uiautomator2 --version
# Should print: 3.7.0 (or newer)
```

**First-time device initialization** (do this once after each factory reset, or if `u2.jar` is missing from the device):

```bash
# Device must be connected via USB or wireless ADB first
/Users/$(whoami)/.local/bin/uiautomator2 init
```

**Using uiautomator2 in Python scripts:**

The pipx-installed package is in its own venv. Add it to sys.path:

```python
import sys
sys.path.insert(0, '/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages')
import uiautomator2 as u2

d = u2.connect('35261JEHN12374')  # USB serial, or '192.168.68.62:5555' for wireless
print(d.info)
```

Common operations:
```python
d(text='OK').click()                          # click by visible text
d(resourceId='com.foo:id/bar').exists         # check if element exists
d.screenshot('/tmp/screen.png')               # take screenshot
```

> **Gotcha:** If `d(text='SomeButton').exists` returns False when the button is visible, another app may have a dismissable popup covering the UI. Click `d(text='OK').click()` to dismiss it first.

### 2.4 SSH key for Termux

```bash
ssh-keygen -t ed25519 -f ~/.ssh/termux_key
# Copy ~/.ssh/termux_key.pub to Termux ~/.ssh/authorized_keys (see Part 1.4)
```

Add to `~/.ssh/config` for convenience:
```
Host termux
  HostName localhost
  Port 8022
  IdentityFile ~/.ssh/termux_key
  User u0_a<UID>
  StrictHostKeyChecking no
```

Connect:
```bash
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh termux
```

### 2.5 Install the Mac-side launchd keepalive

This runs `adb connect` every 60 seconds, handles DHCP IP changes, and sends a macOS notification on reconnect or failure.

**Current (Ansible-generated):** `make deploy` / `site.yml` ends with `control_node/site.yml`
(Homebrew prereqs, `devices.conf`, `com.stayturgid.*` launchd agents). Partial deploys
(`make deploy HOSTS=s24`) also refresh Mac config via `deploy_fleet.py`. Agents launch
`control/bin/adb_reconnect.py` + `control/bin/access_monitor.py`. Logs + state live under
`~/.config/stayturgid/{logs,state}/`.

> The legacy manual path (`cp control/bin/com.djbclark.stayturgid.adb-reconnect.plist …`) is
> superseded by `ansible/playbooks/control_node/agents.yml`; the old `com.djbclark.*` agents were retired.

### 2.6 Install Claude Code (AI development agent)

```bash
npm install -g @anthropic-ai/claude-code
```

The AI agent session runs from `~/upmon-handoff/` (legacy working directory name). Start a session:

```bash
cd ~/upmon-handoff
claude
```

Verify it's using Pro/Max plan (not API billing): run `/status` inside Claude Code.

### 2.7 UI-TARS vision gates (optional)

UI-TARS is a **vendor-neutral Mac sidecar** (`llama-server` on `127.0.0.1:8081`). It is
not stored under `~/.config/stayturgid/` — only fleet config (`devices.conf`, logs,
artifacts) lives there. stayturgid scripts auto-start the server when needed: if launchd is not installed they
run `make vlm-service-install` via Ansible (through `vlm_gate.ensure_server()`), otherwise kickstart
the existing agent.

**One-time setup** (Apple Silicon Mac, ~6 GB disk, 16 GB RAM recommended):

```bash
make configure          # reports llama-server + launchd status
make vlm-install        # Ansible: brew llama.cpp + download GGUF weights
make vlm-service-install   # Ansible: launchd agent homebrew.mxcl.ui-tars
make vlm-check
```

Ansible playbooks: `ansible/playbooks/control_node/vlm.yml` (tags `vlm-models`, `vlm-service`).
Requires `-e stayturgid_vlm_enabled=true` (set automatically by the make targets).

| Scope | Path |
|-------|------|
| UI-TARS home | `~/.local/share/ui-tars/` |
| Models | `~/.local/share/ui-tars/models/1.5-7b/` |
| Server log | `~/Library/Logs/ui-tars/server.log` |
| LaunchAgent | `homebrew.mxcl.ui-tars` |
| stayturgid VLM artifacts | `~/.config/stayturgid/artifacts/vlm-verify/` |

**Upgrading from old `~/.config/stayturgid/models/ui-tars-*` layout:**

```bash
bash control/vlm/ui-tars/vlm_migrate_paths.sh
make vlm-service-install
```

**Day-to-day ops** (launchctl, not a dedicated terminal):

```bash
curl -sf http://127.0.0.1:8081/health
make vlm-service-status
launchctl kickstart -k "gui/$(id -u)/homebrew.mxcl.ui-tars"
make vlm-service-stop
```

Full reference: [docs/vlm.md](vlm.md). Example gate: `make verify-hd8-google HOSTS=hd8`.

---

## Part 3 — Connecting to the device

### Wireless ADB

The device's IP can change across reboots (DHCP). The mac-side script auto-discovers it via USB. To discover manually:

```bash
# Via USB:
adb -s 35261JEHN12374 shell "ip addr show wlan0 | grep 'inet '"
# Then connect wirelessly:
adb connect <discovered-ip>:5555
```

Default/cached IP: `192.168.68.62:5555` (stored in `~/.config/stayturgid/device_ip`).

### SSH to Termux

Direct WiFi SSH is blocked by Android's firewall. Use ADB port-forward:

```bash
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost
```

---

## Part 4 — Development workflow

### Making watchdog changes

1. Edit the JavaScript in `device/autojs6/` on the Mac.
2. Deploy to the device and restart the watchdog:
   ```bash
   ./control/tools/autojs6/deploy.py p7a
   ./control/tools/autojs6/start_watchdog.py p7a
   ```
3. Check the log: `adb shell cat /sdcard/stayturgid/logs/watchdog.log` (or the AutoJs6 console).
4. Commit and push.

### Testing shell scripts off-device (added 2026-07-06)

`device/termux/*.sh` can be exercised on the Mac without a phone: point `HOME` at a
scratch dir and prepend a stub `bin/` (fake `termux-*`, `adb`, `sleep`) to
`PATH`, then assert against the call log the stubs write. The 2026-07-06 code
review validated the battery-alarm tier logic this way.

**pgrep gotcha (bit us in H2 of CODE-REVIEW.md):** on Termux (procps/Linux),
`pgrep -f PATTERN` matches the *caller's own cmdline* — a guard like
`pgrep -f repair-bridge.sh` inside `start-repair-bridge.sh` (or inside an ssh
command string containing the pattern) always self-matches. macOS/BSD pgrep
does **not** do this, so Mac-side dry-runs pass while the on-device guard is
broken. Use pidfiles (`~/.stayturgid/run/repair-bridge.pid` + `/proc/$pid/cmdline`
check) for liveness, and test process guards on the device itself.

**Shell convention:** never assume the user's default shell — macOS defaults
to zsh, Termux users can switch shells, and zsh isn't installed on Termux by
default (`pkg install zsh` if a script genuinely needs it). Declare bash in
every shebang and run remote commands via `ssh host 'bash -s'` (heredoc or
stdin pipe), never bare `ssh host '<commands>'` through the login shell.

### Test suite (three tiers, three idiomatic entry points)

- **Tier a (code):** syntax/lint under local interpreters — `make check` /
  `tests/run.sh code`.
- **Tier b (unit, no device):** shell TAP harness (`tests/test-unit.sh`, runs
  the `battery_suite` against BOTH the shell and Python twins), plain **pytest**
  for the Python script twins (`tests/python/`), and the standard
  **`ansible-test units`** for domain collections (`stayturgid.termux`, `obtainium`,
  `fdroid`, `play` under `ansible_collections/stayturgid/`). `make test` runs all
  three.
- **Tier c (device, read-only):** `make verify` / `tests/run.sh device`.

Setup once: `make test-venv` (builds `.venv-test` with ansible-core + pytest +
pytest-mock + pytest-ansible). CI runs `make test` on every push
(`.github/workflows/test.yml`). `make lint` = shellcheck + ansible-lint +
yamllint. Deploy the fleet with `./control/bin/deploy_fleet.py` (Ansible;
`CHECK=1` for a dry run).

Cheap pre-commit gates (if not running the full `make test`): `bash -n` each
script, `git ls-files '*.sh' | xargs shellcheck -S warning`,
`node --check device/autojs6/**/*.js`, `python3 -m py_compile` the Python sources, and
`ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook ansible/playbooks/fleet/fleet.yml --syntax-check`.

### Using uiautomator2 for device automation

Use for: tapping buttons in app UIs, reading screen state, automating setup steps.

```python
import sys
sys.path.insert(0, '/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages')
import uiautomator2 as u2
d = u2.connect('35261JEHN12374')
```

Run the HTTP server on the device first if it's not running:
```bash
/Users/djbclark/.local/bin/uiautomator2 init
```

### Using Termux:API for device state

Use for: reading battery, clipboard, notifications, sensors — anything that's OS-level rather than UI-level.

```bash
# Via SSH to Termux:
termux-battery-status
termux-clipboard-get
termux-sensor -s "Accelerometer" -n 1
```

### Publishing an update

GitHub `master` is the source of truth; updates are pushed to devices from the Mac.

1. Make changes and test them on a device (`./control/tools/autojs6/deploy.py`, `./control/bin/deploy_termux.py`).
2. Bump `version.json` (`version` + `changelog`) at the repo root.
3. Commit and push.
4. Deploy to the fleet:
   ```bash
   make deploy                    # full site.yml (recommended)
   make verify HOSTS=s24          # optional TAP after deploy
   ```
   Granular: `make deploy-termux`, `control/tools/autojs6/deploy.py <host>` (USB recovery on Fire).

Devices can optionally run `stayturgid_check_repo_version.py` (deployed as `~/stayturgid_check_repo_version.py`; max once/24 h from the boot loop) to get a notification when GitHub's `version.json` is newer than the last deployed version:

```bash
curl -sS https://raw.githubusercontent.com/djbclark/stayturgid/master/version.json
```

---

## Part 5 — Cross-device testing safety rules (discovered 2026-07-01)

### NEVER replace `enabled_accessibility_services` — always append

`settings put secure enabled_accessibility_services <value>` **replaces the entire list**. Running it with just one service wipes every other accessibility service on the device (screen readers, switch access, automation apps, Wispr Flow, Buzzkill — all gone silently).

**Protocol when you need to enable an accessibility service for testing:**

```bash
# 1. Save original list
ORIG=$(adb shell settings get secure enabled_accessibility_services)
echo "ORIG: $ORIG"

# 2. Append new service (do NOT replace)
adb shell settings put secure enabled_accessibility_services \
  "${ORIG}:com.example.app/com.example.app.MyService"

# 3. ... do testing ...

# 4. ALWAYS restore original list when done
adb shell settings put secure enabled_accessibility_services "$ORIG"
```

Also applies to any setting that is a colon-separated list:
`enabled_input_methods`, `enabled_notification_listeners`, etc.

**Verify current state before and after any accessibility change:**
```bash
adb shell settings get secure enabled_accessibility_services | tr ':' '\n'
```

**Fleet backup/restore (preferred):** `control/lib/a11y_profiles.json` holds per-device known-good lists; `control/lib/a11y_backups/<alias>.txt` stores live snapshots. Mac CLI:

```bash
./control/bin/a11y_services.py backup p7a    # snapshot live list → repo + /sdcard/stayturgid/state/
./control/bin/a11y_services.py restore p7a   # merge profile + backup + AutoJs6 (never wipe others)
./control/bin/a11y_services.py show p7a
```

**AutoJs6 drawer accessibility toggle replaces the entire list** — fleet setup uses settings merge only (`enable_autojs6_shizuku.py`), not the drawer switch.

If accessibility services are accidentally wiped, restore from a known-good list recorded at session start. The Pixel 7a's known-good list (as of 2026-07-06; append AutoJs6 — never replace the whole list):
```
com.samruston.buzzkill/com.samruston.buzzkill.background.accessibility.WorkaroundAccessibilityService
com.notch.touch/com.notch.touch.lock.tas
com.wispr.flowapp/com.wispr.flowapp.service.FlowAccessibilityService
org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher
```

Restore (example — verify current list first; **append** new services, never replace):
```bash
adb -s 35261JEHN12374 shell settings put secure enabled_accessibility_services \
  "com.samruston.buzzkill/com.samruston.buzzkill.background.accessibility.WorkaroundAccessibilityService:com.notch.touch/com.notch.touch.lock.tas:com.wispr.flowapp/com.wispr.flowapp.service.FlowAccessibilityService:org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"
```

### At the start of every session: snapshot device state

Before touching any device settings, record:
```bash
adb shell settings get secure enabled_accessibility_services
adb shell settings get secure default_input_method
adb shell settings get global package_verifier_enable
```
…and restore all of them at the end.

---

## Part 5b — Samsung Galaxy S24 specific setup (discovered 2026-07-01)

### Shizuku: "Start via Wireless debugging" fails on Samsung

Samsung's SSL implementation throws `javax.net.ssl.SSLProtocolException: SSLV3_ALERT_CERTIFICATE_UNKNOWN` when Shizuku tries to connect to the Wireless Debugging service on port ~38279. **Do not use "Start via Wireless debugging" on Samsung.**

Use **"Start by connecting to a computer"** instead:
1. Connect device via USB ADB
2. In Shizuku → Settings → "Start by connecting to a computer"
3. Tap "View command" to get the actual path (it changes per install), then run it from Mac:
   ```bash
   adb -s RFCX219CHKA shell /data/app/~~.../moe.shizuku.privileged.api-...=/lib/arm64/libshizuku.so
   ```
4. After Shizuku starts via ADB method, port 5555 does NOT auto-open. Manually trigger:
   ```bash
   adb -s RFCX219CHKA tcpip 5555
   ```

### Battery optimization blocks Shizuku toggles on Samsung

Before Shizuku's "Start on boot" and "Watchdog" toggles will respond:
```bash
adb shell dumpsys deviceidle whitelist +moe.shizuku.privileged.api
```
Then the toggles work.

### Termux: sshd requires explicit environment when started from runit or run-as

On Samsung (tested Android 16), sshd fails silently when started via runit (which uses minimal env). The `runsv sshd` process runs but sshd never actually starts.

**Root cause:** PATH does not include Termux's bin dir, so sshd's wrapper script can't find its deps.

**Fix for runit service** (`$PREFIX/var/service/sshd/run`):
```bash
#!/data/data/com.termux/files/usr/bin/bash
export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH
export HOME=/data/data/com.termux/files/home
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR=/data/data/com.termux/files/usr/tmp
export LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib
exec sshd -D -e 2>&1
```

**run-as with Termux:** Must provide full path to Termux bash AND set env:
```bash
adb -s RFCX219CHKA shell "run-as com.termux /data/data/com.termux/files/usr/bin/bash -c '
  export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:\$PATH
  export HOME=/data/data/com.termux/files/home
  export PREFIX=/data/data/com.termux/files/usr
  sshd
'"
```

**Termux:Boot script** (already includes env vars — see `device/termux/boot/start-adb.sh`).

### `am start -d content://` fails from shell on Samsung/Android 16

On Samsung Android 16, `adb shell am start -d content://com.android.externalstorage...` fails because UID 2000 (shell) cannot grant URI permissions for ExternalStorageProvider. The `--grant-read-uri-permission` flag doesn't help — apps needing file input must use their own file pickers.

### Termux packages: must match signing source

When Termux main app is installed from GitHub releases (via Obtainium), all add-ons must also come from GitHub — not F-Droid. Mixing sources causes `INSTALL_FAILED_SHARED_USER_INCOMPATIBLE`.

GitHub release pages:
- Termux:Boot — `github.com/termux/termux-boot/releases`
- Termux:API — `github.com/termux/termux-api/releases`

If Play Protect blocks the install: `adb shell settings put global package_verifier_enable 0` before installing, re-enable after.

### S24 Termux SSH access (for future sessions)

```bash
adb -s RFCX219CHKA shell "run-as com.termux /data/data/com.termux/files/usr/bin/bash -c '
  export PATH=/data/data/com.termux/files/usr/bin:\$PATH
  export HOME=/data/data/com.termux/files/home
  pkill sshd 2>/dev/null; sshd
'"
adb -s RFCX219CHKA forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 -o StrictHostKeyChecking=no localhost
```

After SSH is up, all further setup can be done cleanly without dealing with terminal background noise.

---

## Part 6 — Verification checklist

After a cold reboot and PIN unlock, wait ~60 seconds, then run from the Mac:

```bash
# 1. Check port 5555 is open (Shizuku TCP mode did its job)
adb -s 35261JEHN12374 shell "ss -tln 2>/dev/null | grep ':5555'"
# Expected: LISTEN line for :5555

# 2. Connect wirelessly
adb connect 192.168.68.62:5555
# Expected: "connected to 192.168.68.62:5555"

# 3. Check sshd is running (Termux:Boot did its job)
adb shell "ss -tln 2>/dev/null | grep ':8022'"
# Expected: LISTEN line for :8022

# 4. Check Shizuku process
adb shell "pgrep -f shizuku && echo SHIZUKU_OK"
# Expected: SHIZUKU_OK

# 5. SSH into Termux
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost "echo SSH_OK"
# Expected: SSH_OK
```

If port 5555 is not open after 60s:
- Check Shizuku is running: `adb shell pgrep -f shizuku`
- Check TCP mode is ON in Shizuku Settings
- Manually trigger: `adb shell "run-as com.termux sh -c 'adb tcpip 5555'"`

---

## Part 6b — F-Droid / Neo Store + Play / Aurora (parked)

**Not** part of active `./control/bin/deploy_fleet.py` (2026-07-09). Set
`stayturgid_app_stores_enabled: true` to re-enable. Apps may remain on devices;
optional Obtainium catalog: `catalogs/obtainium/app-stores-optional.json`.

When re-enabled: second `fleet.yml` pass (`post-ui-app-stores` tag) pushes F-Droid
repos; `post-ui.yml` / `android_ui` task `configure_aurora` finishes Aurora first-run UI.

| Command | Scope | Mac tools |
|---------|-------|-----------|
| `make deploy [HOSTS=…]` | Full `site.yml` (includes preflight) | fdroidcl, apkeep when stores on |
| `make deploy SCOPE=fdroid HOSTS=…` | F-Droid tags only | fdroidcl |
| `make deploy SCOPE=play HOSTS=…` | Play + post-ui Aurora | apkeep |

**Default repos** (`ansible_collections/stayturgid/fdroid/roles/fdroid_repos/defaults/main.yml`):

| Name | URL | SHA-256 fingerprint |
|------|-----|---------------------|
| IzzyOnDroid | `https://apt.izzysoft.de/fdroid/repo` | `3BF0D6ABFEAE2F401707B6D966BE743BF0EEE49C2561B9BA39073711F628937A` |
| Guardian Project | `https://guardianproject.info/fdroid/repo` | `B7C2EEFD8DAC7806AF67DFCD92EB18126BC08312A7F2D6F3862E46013C7A6135` |

**Install from Mac after fleet deploy:**

```bash
ANDROID_SERIAL="$(resolve_adb s24)" fdroidcl install com.example.app
```

**Shizuku grants** (privileged adb): `stayturgid.android_common.shizuku_grant` Ansible module, or `ansible-playbook` via fdroid/play roles.

**Historical E2E (2026-07-07, pre-park):** fdroidcl install smoke test on s24/p7a/hd8; uninstalled after verify.

See [docs/modules/fdroid.md](modules/fdroid.md), [modules/fdroid.md](modules/fdroid.md), [modules/play.md](modules/play.md).

---

## Repo structure

```
device/autojs6/
  main.js  lib/  devices/  scripts/     — AutoJs6 watchdog project
control/tools/autojs6/                    — deploy.py, setup_autojs6.py, grant_shizuku.py, start_watchdog.py
device/termux/
  boot/start-adb.sh                     — deploy to ~/.termux/boot/ on device
  stayturgid_repair.py                  — Termux-side self-heal
  stayturgid_check_repo_version.py      — optional update notifier (Python)
ansible/                                — idempotent Termux userland deploy
control/bin/                            — adb_reconnect.py, access_monitor.py (launchd via control_node/agents)
catalogs/obtainium/                     — APK tracking catalogs
control/lib/                            — resolve_adb.py, stayturgid_device.py, adb_cli.py
ansible/playbooks/fleet/fleet.yml       — full fleet (includes fdroid + play roles)
ansible/playbooks/site.yml              — full fleet (preflight → … → validate)
docs/hacking.md                         — this file
docs/handoff.md                         — AI session handoff prompt
README.md                               — user-facing setup guide
```
