# stayturgid-agent (native Kotlin)

OPTIONS **K1** is a purpose-built APK that binds a **Shizuku UserService**
(UID 2000) and injects silent input via `InputManager.injectInputEvent` —
**no** shell spawn, **no** Accessibility.

The agent also writes a 20-minute co-monitor heartbeat, repairs the Shizuku
shell path, and requests a Tailscale reconnect when either the tunnel or
remote Tailscale control-plane reachability is down. A repair is reported
successful only after both are re-probed as healthy. It also restores the configured
non-lockdown always-on VPN policy. Termux remains the primary sshd and routine
repair owner.

History (K1 cutover): checkpoint
[`docs/operations/sessions/session-2026-07-22-native-agent.md`](../../docs/operations/sessions/session-2026-07-22-native-agent.md).
Current status: [docs/STATUS.md](../../docs/STATUS.md).

## Package

| Item            | Value                  |
| --------------- | ---------------------- |
| applicationId   | `org.stayturgid.agent` |
| debug suffix    | `.debug`               |
| minSdk / target | 26 / 36                |

## Build

**Built on GitHub CI only, never on the Mac (djbclark, 2026-10-18; it was Forgejo
CI on SIPB's Hyades from 2026-10-17).** Since 2026-11-21 a push to `master` that
touches this directory builds, signs and publishes the agent as a rolling
release, with nothing to run by hand; see [Rolling releases](#rolling-releases).
To test a branch without publishing, `just agent-ci-run BRANCH` and
`just agent-ci-fetch` (the fallback below). `just kt-test`, `kt-build-*` and
`agent-assemble` refuse to run locally; spotless and detekt (the pre-commit
hooks) stay local. GitHub runners need no loopback shim; that is a Hyades
(libkrun) workaround. `.forgejo/` in this repo is the retired Forgejo flow.

## Rolling releases

Operator decision 2026-11-21: rolling releases, no pins, breakage accepted.
`.github/workflows/agent-release.yml` is the whole flow; its logic is in
`scripts/ci/agent_release.py`.

**Trigger.** A push to `master` that touches `device/native-agent/` (not
`*.md`), or a manual dispatch by someone with write access. There is no
`pull_request` trigger, so a fork can never reach a secret.

**Jobs.**

1. `build` has no secret and a read-only token. It runs Gradle (unit tests,
   detekt, `assembleRelease`) and uploads the unsigned APK as the artifact
   `agent-unsigned` (kept 14 days).
2. `check` has no secret and a read-only token. It is the first reader of the
   Gradle-built APK: it verifies the SHA-256 and that the APK is the package
   `org.stayturgid.agent` with the `versionCode` it was built with.
3. `sign` runs in the GitHub environment `agent-release`, which GitHub restricts
   to the `master` branch. It has the release key and no write token: it runs
   `apksigner` and uploads the signed APK as the artifact `agent-signed`.
4. `verify` has no secret and a read-only token. It re-reads the signed APK: the
   signer certificate's SHA-256 is exactly the fleet's (`35bbc3d1…`, the same key
   as before so installed apps update in place), the package is ours, and the
   `versionCode` equals the number in the tag. It approves that file's SHA-256.
5. `release` has the `contents: write` token and no key, and parses nothing: it
   publishes only the file with the approved digest, as a normal (not pre-)
   release tagged `agent-r<versionCode>` with exactly one asset, `app-release.apk`
   (and refuses a tag that already points at another commit). It then prunes to
   the newest 10 `agent-r*` releases (the git tags stay, see the tag ruleset
   below). The older `agent-ci-*` prereleases are no longer published (existing
   ones stay); they and `agent-v*` are separate tag streams.

No job runs Gradle except `build`, and no runner ever holds both the key and the
write token.

**Versioning.** `versionCode` = `GITHUB_RUN_NUMBER` + 100, so the first rolling
build is above the last hand-made one (37). `versionName` =
`0.9.<versionCode>+<sha8>`. Gradle reads `AGENT_VERSION_CODE` and
`AGENT_VERSION_NAME`; without them (local or fork builds) it uses 37 and 0.9.19.

**Consumers follow the newest release; the signer is pinned, not the version.**
`bootstrap_apks` installs the agent with `gh_latest` plus `gh_tag_prefix: agent-r`
and `gh_pattern: app-release.apk`, comparing the installed `base.apk` SHA-256 with
the asset digest GitHub publishes. Because a release is only as trustworthy as
whoever can create one, the entry also sets `signer_sha256` (the fleet release
certificate): before anything is installed the module checks, with `apksigner`
and `aapt2`, that the APK carries exactly that certificate and is the package
`org.stayturgid.agent`, on a fresh phone too. A rolling entry never takes the
clean-uninstall fallback on a signature mismatch. On the device, `UpdateCheck.kt`
watches the tags `agent-r<versionCode>` and compares them with
`BuildConfig.VERSION_CODE`.

**Secrets (names only).** Three secrets of the environment `agent-release` of
`djbclark/stayturgid`: `STAYTURGID_AGENT_KEYSTORE_B64`,
`STAYTURGID_AGENT_KEYSTORE_PASSWORD` and `STAYTURGID_AGENT_KEY_PASSWORD`. The key
alias (`agent`) is not secret, so it is a plain value (a secret is masked
everywhere its word appears in a log). They were set from the local, gitignored
`agent-release.jks`, which stays on the Mac for the fallback. To rotate or re-set
one, run `gh secret set NAME --env agent-release` with the value on stdin, never
on the command line.

**Trust boundaries** (this is a public repository):

- No `pull_request` trigger; only a push to `master` or a write-access dispatch.
- The `build` job, which runs repo code and third-party Gradle plugins, never
  sees a secret.
- `check`, `sign`, `verify` and `release` run only `scripts/ci/agent_release.py` and first-party
  actions pinned by commit. `check` has no secret; `sign` has the key and no token;
  `verify` reads the signed APK with no secret and no write token; `release` has the token and no key and
  publishes only what `verify` approved. Only
  `apksigner` is handed the two passwords, and nothing parses the signed output
  while the key is in the environment. The one remaining exposure: a crafted APK
  that exploits `apksigner` itself, in `sign`, could reach the key there.
- A dispatch from any other branch cannot read the environment's secrets, and the
  `check`, `sign`, `verify` and `release` jobs are skipped there. A branch dispatch has its
  own concurrency group, so it cannot replace a pending master release.
- **Tag rulesets** on `djbclark/stayturgid` (`agent-r tags: only the release workflow creates` and
  `agent-r tags: no update or delete`), target `refs/tags/agent-r*`. The first restricts creating
  those tags; its bypass actors are the GitHub Actions integration (every Actions token with
  `contents: write`, not this workflow alone) and repository admins (the shared Mac `gh` token
  is one). The second forbids updating and deleting them, with no bypass (an admin disables the
  ruleset to change one on purpose). `agent-release.yml` never deletes a tag: pruning and
  repairing delete the release only, and `release` refuses an existing tag that points at
  another commit. Creating a release on an old existing tag creates no ref, so the rulesets do
  not stop it; the client side does: `gh_latest` takes the highest `agent-r<N>` number, not the
  first listed, and refuses an APK whose `versionCode` is not the tag's number.
- `gh_latest` accepts a release only if its whole tag is `agent-r` plus a version
  number (`agent-rz`, `agent-r1x` and `agent-r1-evil` are ignored).
- The phones do not trust the workflow alone: the signer pin above holds even if a
  release is created some other way.

**Fallback (unsigned build, signed on the Mac).** `just agent-ci-run BRANCH`
dispatches the workflow with `sign=false`: it builds and tests but publishes
nothing and keeps the unsigned APK as the artifact `agent-unsigned`. Then
`just agent-ci-fetch [FULL_SHA]` downloads that artifact, checks its SHA-256,
signs it with the local `agent-release.jks` (`ci_fetch_sign.py`) and checks the
signer, writing `app/build/outputs/apk/release/app-release.apk`.

## Local build and install

The local build below is kept for reference only. It requires Android SDK (`ANDROID_HOME` or `local.properties` `sdk.dir`) and
**JDK 17 or 21** (AGP 8.10 rejects JDK 25+). On this Mac:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
```

```bash
cd device/native-agent
# optional: point at local Shizuku API fork (default $HOME/src/Shizuku/api)
# export SHIZUKU_API_DIR=$HOME/src/Shizuku/api
./gradlew :app:assembleDebug
```

Default build uses `dev.rikka.shizuku:api` from Maven Central. A **Gradle
composite** against `$HOME/src/Shizuku/api` is opt-in (it was the default
until 2026-09-29, when that checkout's move to AGP 9.2.1 / Gradle 9.4.1 broke
every build on this wrapper):

```bash
./gradlew :app:assembleDebug -Pshizuku.composite=true
```

APK path:

```text
app/build/outputs/apk/debug/app-debug.apk
```

From repo root:

```bash
just agent-assemble
just agent-rollout              # reachable hosts from devices.conf
just agent-rollout p7a s24      # subset
just agent-install 100.x.x.x:5555
just agent-grant p7a
just agent-start p7a
```

Live fleet status: [docs/STATUS.md](../../docs/STATUS.md). The 2026-07-22
snapshot is archived at
[docs/archive/plans/native-agent-status-2026-07-22.md](../../docs/archive/plans/native-agent-status-2026-07-22.md).

## Install / pilot

```bash
adb -s <serial> install -r app/build/outputs/apk/debug/app-debug.apk
adb -s <serial> shell am start -n org.stayturgid.agent.debug/.MainActivity
```

1. Ensure Shizuku is running (fleet fork).
2. Open app → **Request Shizuku permission** → grant in Shizuku.
3. **Start host service** (or reboot — `BootReceiver` starts FGS).
4. With screen on, logcat should show `StayTurgidUS: pingAwake ok` and
   `StayTurgidHost: pingAwake IPC ok` (immediate + every 5 min).

```bash
adb logcat -s StayTurgidHost:I StayTurgidUS:I StayTurgidMain:I StayTurgidApp:I StayTurgidBoot:I
```

## Architecture

- `HostService` — FGS (`specialUse`), `SCREEN_ON`/`OFF`, coroutine timer
- `ShizukuUserService` — AIDL stub for keep-awake, co-monitor, shell repair,
  and Tailscale relaunch
- `ComonitorProbes` — STATUS for port 5555, Shizuku, sshd, a11y, Wi-Fi, and
  Tailscale; port probing falls back to `ss -ltn` on Fire OS when `/proc`
  hides adbd
- `CatastrophicRepair` — requests Tailscale reconnect through the app's
  exported receiver, falls back to its activity, and fails honestly when an
  app/runtime incompatibility still requires operator input
- Shizuku API: `dev.rikka.shizuku:api` / `:provider` from Maven Central by
  default; optional composite build against a local fork
  (`-Pshizuku.composite=true`)
- `HandsetsStarter`/`HandsetsStartCommands` — peer-start the Handsets UI
  daemon on a Fire-OS device over external ADB (issue #121), the same
  no-Mac-dependency shape as `PeerStarter`'s Shizuku peer-start (issue #61)

The Termux twin in `device/termux/py/stayturgid_repair.py` runs every five
minutes and enforces the same runtime and always-on policy checks.

`app/src/main/assets/hs.jar` bundles the Handsets daemon (MIT-licensed,
Elliot Gao) so the agent can push it without the Mac having a copy; the
required license/copyright notice ships alongside it as the companion asset
`app/src/main/assets/hs.jar.LICENSE.txt`.

Quiet mode (0.9.18): the launcher shows "Audio alerts: ON" or "OFF until
<time>", with **Quiet until morning (09:00)** (the end of the usual 21:00-09:00
sleeping window), **Quiet until 10:00 tomorrow** (this replaced the old "No
nightly battery warnings today" button) and **Turn audio alerts back on**.
Quiet buttons stop a locate sound that is playing and turn the flashlight off.
`QuietMode` keeps the deadline, `LocateSound` refuses to play while it lasts
(an explicit `ring` still plays), and the agent hands the same deadline to
`stayturgid_battery_alarm.py quiet-until <epoch>`. At the end of every
flashlight alarm, Termux sends `org.stayturgid.agent.action.TORCH_OFF` and
`Torch` checks the real torch state through `CameraManager`.

The launcher UI shows the version name/code, UTC build time, source revision,
application ID, build type, Android/device identity, and live Shizuku state.
The full diagnostic block is selectable and can be copied with one button.

## Non-goals

The agent does not replace the Termux primary repair loop, restart Termux
sshd, or enable Accessibility.
