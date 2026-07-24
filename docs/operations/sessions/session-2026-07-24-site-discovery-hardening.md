# Session 2026-07-24 — site-discovery hardening

**Status:** implementation complete on review branches; merge pending operator
confirmation.

## Scope

Complete [#48](https://github.com/djbclark/stayturgid/issues/48) across
`stayturgid`, `site-djbclark`, and `site-private`:

- one shared implicit site resolver;
- `OPS_ROOT/.mysite` precedence;
- exclusion of the reserved and configured private companion;
- selected path/source announcements;
- safe missing-companion bootstrap; and
- current documentation in all three policy slices.

## Implementation

- Added `control/lib/site_discovery.py` as the shared authority used by Ansible
  context resolution, Site Contract commands, and landing discovery.
- Precedence is `ANSIBLE_CONFIG` (where applicable),
  `STAYTURGID_SITE_DIR`, `OPS_ROOT/.mysite`, then exactly one qualifying
  `site-*` checkout.
- Literal `site-private` and `STAYTURGID_PRIVATE_DIR` are never site-overlay
  candidates. `site-init sitename=private` and an explicit private-companion
  destination fail closed.
- A missing private companion is created as an owner-only empty directory.
  Product code never guesses a private Git remote, initializes Git, or creates
  secrets.
- Successful resolution prints the selected site directory and precedence
  source.

## Safety

- The operator-authored uncommitted
  `site-djbclark/human/F2-BREW-SERVICES-DECISIONS.md` was not touched.
- Merge remains gated on operator review of verification evidence.

## Unrelated baseline repairs

The operator authorized fixing unrelated failures found during verification.
The same failures were reproduced against untouched `origin/master` before
repair:

- Fleet-health tests still asserted retired watchdog behavior. They now cover
  native-agent missing/stale semantics and the agent heal cooldown.
- The fallback Obtainium catalog still contained retired AutoJs6 although role
  defaults are authoritative. The stale entry was removed.
- The healing registry mechanically assigned sshd, Accessibility, and
  Tailscale to the native agent during K1. Its accepted scope does not include
  sshd or Accessibility, so those false requirements were removed. The
  actually lost Tailscale runtime probe/relaunch was implemented in the native
  agent.
- USB-backed hd8 testing found that Fire OS hides the live adbd listener from
  `/proc/net/tcp`; the agent now falls back to `ss -ltn` instead of
  false-reporting `CLOSED_NO_SHELL`.
- Forced-down hd8 testing found that Tailscale 1.98.8's exported
  `CONNECT_VPN` receiver reaches `StartVPNWorker`, but Fire OS rejects that
  expedited worker because it does not implement `getForegroundInfo()`. The
  agent now tries the receiver before its activity fallback and reports repair
  success only after a healthy tunnel re-probe. This runtime combination still
  requires an unlocked operator action after an app force-stop.
- The same live test found hd8's declared always-on VPN setting missing. The
  Ansible role is now registered as the deploy implementation, the Termux
  5-minute loop is the self-heal twin, and the native shell path repairs the
  setting before attempting runtime reconnect.
- Final rollout found that Shizuku could leave an old agent UserService alive
  beside the new one. Rollout now kills stale UserServices and requires exactly
  one host, one UserService, and a current-format STATUS before reporting OK.
- The retired `WATCHDOG-FRESH` state and dead Mac watchdog-heal remnants were
  removed; legacy fields remain telemetry-only pending fleet-state
  verification.

## Verification

- `just test`: PASS — 133 TAP unit checks, 567 pytest tests plus one skip, and
  all `android_common`, `termux`, `obtainium`, `fdroid`, and `play` Ansible
  unit collections.
- `just check`: PASS, including site-contract Entangled parity, all linters,
  generated-source checks, and public identity/secret drift checks.
- Android debug APK: JDK 21 `:app:assembleDebug` PASS; v0.3.6
  (`versionCode=10`) installed on all three fleet devices. Its launcher shows
  and can copy version/build/time/revision and runtime diagnostics.
- hd8 (USB-backed): fresh status reported `port=open`, `shizuku=up`,
  `sshd=up`, `tailscale=up`, and `tailscale_policy=up`. A forced policy drift
  to no always-on app was restored to `com.tailscale.ipn` with lockdown off
  while Tailscale control-plane reachability stayed up.
- s24: rollout completed without stopping Tailscale; fresh status reported
  `port=open`, `shizuku=up`, `sshd=up`, `tailscale=up`, and
  `tailscale_policy=up`.
- p7a: rollout found the Tailscale always-on policy unset, repaired it, and
  wrote a fresh status reporting `port=open`, `shizuku=up`, `sshd=up`,
  `tailscale=up`, and `tailscale_policy=up`.
- `site-djbclark`: registry lint and focused Prettier check PASS.
  `site-private`: focused Prettier and diff checks PASS.
- Pre-change rollback APKs were captured locally for the initial hd8 and s24
  pilots. The
  operator-authored dirty site decision file remained untouched and is
  excluded from this change set.
