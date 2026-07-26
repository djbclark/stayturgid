# Lessons learned

Session-learned gotchas and conventions for developing and operating
stayturgid — narrower and more anecdotal than
[docs/coding-rules.md](../coding-rules.md) (durable rules) or
[docs/rules/](../rules/) (always-on policies), but still worth reading before
you hit the same problem someone already hit. Imported 2026-07-23 from Claude
Code memory as part of moving cross-session AI memory into git — see
[docs/architecture/multi-site-topology.md](../architecture/multi-site-topology.md)
for the memory/site-documentation policy that governs where this kind of
content lives.

## Device fleet operational gotchas

### Shell assumptions — never assume the default shell

Code must never assume which shell a user runs by default. macOS defaults to
zsh, Termux users may switch to fish/zsh, and **zsh is NOT installed on
Termux by default**. A bare `ssh host '<commands>'` runs through the login
shell and breaks under fish (`$( )`, `[ ]` chains, `printf %q` output are
bash-isms).

**How to apply:** every script declares bash in its shebang; remote commands
go via `ssh host 'bash -s'` with a heredoc or stdin pipe; install zsh
(`pkg install zsh`) only if genuinely needed.

### Notification shade audit

Whenever working with one of the Android devices (in the course of other
work), check the active notifications: confirm the ones up are expected and
correct, and that expected ones (e.g. an active presence notification during
a session, a battery-tier alert when low) aren't missing.

**Why:** zombie/spam notifications (legacy Tasker, AutoJs6 blocked-loop) went
unnoticed in the past; missing ones can mean a dead watchdog.

**How to apply:** read-only probe: `adb shell dumpsys notification
--noredact` filtered for stayturgid/termux/autojs6/tasker records; compare
against what the current device state should show.

### Obtainium over Play Store / F-Droid

For the stayturgid Android devices, **always prefer Obtainium (GitHub
sources) over both Google Play Store and F-Droid** wherever it makes sense.
If an app was installed from Play or F-Droid, re-install it via Obtainium
without asking — every time, proactively.

**Why:** consistency and control. Concretely for Termux: the Play Store
Termux build lacks a working `termux-api`, and mixing sources breaks the
ecosystem — all `com.termux` apps that share `sharedUserId="com.termux"`
(api, boot, tasker, styling, widget, window/float, gui — NOT x11, NOT
third-party intent apps) MUST share one signature or the install fails with
`INSTALL_FAILED_SHARED_USER_INCOMPATIBLE`. GitHub-via-Obtainium builds are
consistently signed and match each other. Third-party Termux apps
(`io.github.*`, etc.) don't share the uid and can stay wherever they are.

**How to apply:** uninstall the Play/F-Droid build and install the GitHub
build via Obtainium (deep link
`obtainium://add/https://github.com/<owner>/<repo>`; Obtainium is a Flutter
app — tap by coordinate, its AX tree is sparse). Replacing Termux wipes
`/data/data/com.termux` — back up `$HOME` first (SSH keys, `.termux/boot`),
reinstall pkgs, restore. ADB-over-Tailscale via Shizuku survives the swap
(safety net). Even when the initial install is via `adb install` (e.g. to
bypass Play Protect's biometric gate on old-`targetSdk` APKs), **always add
the app to Obtainium afterward** so future updates auto-install.

### AutoInput crash-loop root cause (resolved 2026-07-05, historical)

AutoInput crash-loop ("AutoInput keeps stopping", Pixel 7a Android 16).
**Confirmed root cause** from `dumpsys dropbox --print`:
`ForegroundServiceStartNotAllowedException` on
`com.joaomgcd.autoinput/.service.ServiceDismissKeyguard` — the "Auto Dismiss
Keyguard" standalone feature starts a foreground service on every screen-on,
which Android 12+/16 blocks for background apps.

**Fix that worked:** battery-optimization **Unrestricted/exempt** for
AutoInput/Tasker/Tasker Settings — battery-exempt apps may start the
background FGS. Kept "Accessibility In Foreground" ON rather than switching
to "Enable Just When Needed" (contradictory, and toggling the a11y service
risks the enabled-services list — see the append-not-replace rule in
[coding-rules.md](../coding-rules.md)). If it recurs: disable Auto Dismiss
Keyguard and/or update AutoInput.

**Watchdog implication:** don't dismiss keyguard from background via
AutoInput; prefer `adb -s localhost:5555 shell input ...` while 5555 is up,
reserve AutoInput for the catastrophic 5555-down case.

### Termux SSH aliases

SSH into the fleet devices via aliases in `~/.ssh/config` (e.g. `ssh s24`,
`ssh p7a`) over Tailscale, port 8022, no USB/port-forward needed.

**Critical:** a global `Host *` block that routes `IdentityAgent` through
1Password will pop an unlock dialog on every ssh to a phone. The device
blocks must sit ABOVE `Host *` (first-match wins) and set
`IdentityAgent none` + `IdentitiesOnly yes` + an explicit `IdentityFile`.
Never route the phones through the 1Password agent — other hosts (github,
etc.) can keep using it.

Termux sshd authenticates by key and ignores the login username. Device
`authorized_keys` needs the matching public key; if `run-as` is blocked
(non-debuggable Termux), deploy via `/sdcard` +
`android.permission.READ_EXTERNAL_STORAGE`.

### Termux sshd restart gotchas

Two gotchas hit on the fleet:

1. **Never `pkill; sshd` via `run-as com.termux`.** OpenSSH propagates
   sshd's own env PATH to non-interactive sessions. `run-as` gives sshd the
   Android-only PATH, so `ssh host 'bash -s'` then fails with
   `bash: command not found`. Always restart sshd with the full Termux env
   exported first: `export PATH=$PREFIX/bin:$PREFIX/sbin:$PATH
HOME=... PREFIX=... TMPDIR=$PREFIX/tmp
LD_LIBRARY_PATH=$PREFIX/lib; sshd`. Recovery is painful — competing boot
   loops resurrect a running bad sshd (repair only starts sshd when DOWN),
   and SELinux hides other-uid sockets from `run-as`'s `ss` (use shell-uid
   `netstat` / `/proc/net/tcp`, port 8022 = hex `1F5E`). Kill the bad sshd by
   explicit PID via `run-as`, confirm dead, then start with the full env — or
   just `adb reboot` (needs PIN re-unlock).
2. **OpenSSH 9.8+ `PerSourcePenalties` can lock the operator out.**
   Automation bursts / aborted connections penalize the source IP.
   stayturgid sets `PerSourcePenalties no` via Ansible (key-only,
   Tailscale/LAN-only sshds — the penalty protects nothing here). Device tier
   asserts it.

## Repo / PR review notes

### CodeRabbit sometimes misapplies AGENTS.md conventions

CodeRabbit's review on stayturgid PRs has flagged Python/TypeScript library
functions for missing AGENTS.md conventions
("announce before device interaction", "requires `ScreenControlSession`")
against code they don't actually apply to — an Ansible `module_utils`
function invoked during a playbook run, and an on-device Rhino watchdog
script with no screen-control concept at all.

**Why:** both conventions are scoped elsewhere. "Announce before device
interaction" is a directive for the AI _agent_ to warn the operator in chat
before running something against live hardware during a session — not a
code-level logging requirement for library functions. `ScreenControlSession`
(`control/lib/screen_control.py`) is Mac-side tooling for multi-project
remote screen-control lease arbitration — it has nothing to do with
autonomous on-device scripts.

**How to apply:** when a reviewer cites an AGENTS.md convention against code
in `device/autojs6/`, `ansible_collections/`, or similar autonomous/on-device
paths, don't implement it reflexively — `grep` the convention's real usage
sites first and check whether the flagged file's context (interactive AI
session vs. autonomous script vs. Mac-side tooling) actually matches. This
doesn't mean dismiss automated review by default — verify each finding
independently against the actual codebase.

### Generated-file verification scope

When reviewing/building tooling around committed generated files (e.g.
compiled `.js` alongside source `.ts`), the bar is **not** "a fresh rebuild
must be byte-for-byte identical to what's committed." Don't design CI/
pre-commit checks that recompile to a temp dir and diff against committed
output, or otherwise enforce exact toolchain reproducibility.

**How to apply:** for generated/compiled-and-committed file pairs, the right
verification bar is (1) every source file has a correspondingly-named
generated counterpart, (2) the generated file is _functionally_ correct (no
semantic drift — verify by reading/diffing logic, not literal bytes), (3) any
required markers (e.g. a `// @generated` header) are present. A cosmetic
formatting mismatch on regeneration is fine to note, not a blocking must-fix.

## Session wrap-up protocol

At the end of every substantial session, leave enough context/tokens to
complete these steps before running out:

1. Update `docs/STATUS.md` (or the relevant session doc) with current project
   status — what's done, what's next, any architecture changes.
2. Push all changes to GitHub.
3. If a device screen was used, change the Android keyboard back to an
   interactive human-use keyboard (default: GBoard —
   `com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME`).
   Check the current IME with
   `adb shell settings get secure default_input_method` before changing, and
   restore to whatever it was at session start if it wasn't already GBoard.

**Why:** sessions should always end in a clean, committed, handoff-ready
state regardless of how much work happened.

**How to apply:** budget for these steps proactively — if the conversation is
getting long, do the wrap-up before context fills up rather than after. A
resource-exhaustion symptom near the end of a long context window can look
like a tool failure even though prior Edit-tool writes already persisted to
disk — so **commit + push at every logical milestone**, not just at the end,
and record important decisions/TODOs before starting the work they describe,
so plans survive an unfinished task.

## Directory layout (${OPS_ROOT:-~/ops} convention)

The permanent base dir is `${OPS_ROOT:-~/ops}`, with three sibling checkouts:
`${OPS_ROOT:-~/ops}/stayturgid` (this repo, always public), `${OPS_ROOT:-~/ops}/site-<name>` (one
operator's private-or-public site overlay — inventory, credentials-adjacent
config, per-site process), and `${OPS_ROOT:-~/ops}/site-private` (always private,
statically named the same for every operator — anything not managed by
either of the other two). See
[multi-site-topology.md](../architecture/multi-site-topology.md) for the
full policy, including what goes where and how Claude Code's memory system
uses `site-private`.

Check `registry/ports.yml` (in the site overlay repo) before assigning any
new listen port.

## Observability stack decision (O-V-G-O over ONGAO)

stayturgid's fleet observability/control stack is **O-V-G-O** (OpenObserve +
VictoriaMetrics + Grafana + OliveTin) — not the earlier ONGAO plan
(OpenObserve + Netdata + Grafana + Aurora + OliveTin). Full rationale:
[docs/architecture/platform-architecture.md §6.2](../architecture/platform-architecture.md#62-why-o-v-g-o-not-ongao-not-elk).
`docs/archive/plans/ongao-rollout-plan.md` is superseded, historical only —
follow the O-V-G-O docs for any observability work.

## Agent peer-start: trigger via broadcast, and Fire-OS ADB auth is a human tap (#61)

Two gotchas from building the external-ADB Shizuku peer-starter into the
`stayturgid-agent` APK (issue #61):

- **Trigger a background action with a broadcast, never an activity.** The first
  manual-kick path launched `MainActivity` with an intent extra, which forced
  the agent GUI to the foreground on every trigger — operator-visible and
  disruptive. Use an exported `BroadcastReceiver` (`am broadcast -a … -n
<pkg>/<receiver>`) that forwards to the already-running FGS; it never
  foregrounds the UI. Steady-state peer-start is an in-process `HostService`
  loop (also headless). The agent should only come to the foreground when a
  human opens it.
- **Authorizing a _new_ ADB key on Fire OS is a manual "Always allow" tap.**
  `/data/misc/adb/adb_keys` is root-only; adbd writes it solely after the
  `UsbDebuggingActivity` dialog is confirmed **with the "Always allow" checkbox
  ticked**. `control/lib/adb_cli.dismiss_usb_debugging_dialog`'s
  TAB/SPACE/ENTER keyevent heuristic does _not_ reliably tick that checkbox on
  Fire OS 8 — it accepts allow-once, so the dialog reappears on the next
  connect and the key never persists. This is the deliberate one-time cost of
  the per-device key model (agent generates its own key, à la Shizuku's
  `AdbKey`, rather than sharing the fleet key): one physical tap per peer, then
  it survives reboots. Don't try to automate it; do the tap. The full ADB
  handshake up to that gate (CNXN → AUTH token → signature → RSAPUBLICKEY) is
  exercisable and was validated live s24→hd8.

## Termux (app uid) can't read /proc/net on modern Android — route device reads through uid 2000 (#64)

On Android 10+ SELinux restricts `/proc/net/*` per-uid: the **Termux app uid
cannot read `/proc/net/dev`** (EACCES), while the **shell uid (2000)** can. A
device-state check that reads `/proc/net/*` directly in a Termux Python process
silently fails and reads the state as absent. This bit `stayturgid_repair.py`'s
`_tailscale_runtime_up()`: it read `/proc/net/dev` in-process to detect the
tunnel interface, always got EACCES, concluded the tunnel was down every cycle,
and (with the deferred foreground fallback) launched Tailscale's `MainActivity`
into the foreground ~every 15 min despite a healthy tunnel. The native agent
read the same file fine because it runs as uid 2000.

**How to apply:** any device/network state a Termux-side script needs from
`/proc/net/*` (tunnel ifaces, listening sockets, routes) must be read through
the device shell — `sh_adb(...)` / `adb -s localhost:5555 shell` (uid 2000) — not
Python's `open()` in the Termux process. The native agent (uid 2000 via Shizuku)
can read them directly. Same class of bug as the `ss`/`/proc/net/tcp` fallbacks
in the agent's `listeningOn()`.

## One agent per device: debug and release builds install side-by-side

The native agent's debug build uses `applicationIdSuffix ".debug"`, so
`org.stayturgid.agent` (release) and `org.stayturgid.agent.debug` (debug) are
**different package ids** and install concurrently — each runs its own
`HostService` foreground service, giving two non-dismissable "UserService
bound" notifications and two agents racing to bind Shizuku. `adb install -r`
only ever replaces the _same_ package, so it never clears the other build.

**How to apply:** installing the agent must enforce a single build per device —
force-stop + `pm uninstall` the other variant, and force-stop the keeper's old
processes, _before_ `adb install -r`. This lives in
`control/tools/native-agent/rollout.py:enforce_single_variant()` and the
`just agent-install` recipe; `just agent-dedupe [target]` audits/repairs a
device on demand. The fleet keeps the **debug** build (provisioning's `run-as`
needs a debuggable build). Found on hd8 and s24 (both had release 0.3.x left
over under the newer debug build).
