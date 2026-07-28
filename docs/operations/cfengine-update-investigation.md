# CFEngine update investigation (#63)

## Current state

- **Control node (Mac):** CFEngine Core **3.27.1**, installed via a
  vendored, versioned Homebrew formula
  (`packaging/homebrew/cfengine@3.27.1.rb`, tapped as
  `cfengine-local/cfengine`) and pinned via `brew pin` so `brew upgrade`
  can't bump it — see `ansible/roles/control_node/tasks/prereqs.yml`. The pin's
  own comment is explicit about why: _"we want the version pinned to the
  Termux fleet (3.27.1), not homebrew-core's latest."_
- **Fleet (Termux/Android):** CFEngine Core **3.27.1** (`1:3.27.1` per
  `apt`), confirmed live on hd8 via SSH — matches the control node exactly,
  as intended.
- **Latest CFEngine Community release:** **3.28.0**, released 2026-07-10
  (per cfengine.com's release feed).

## Why the control node and fleet are pinned together

`just cf-run` is **pure SSH** — for each device it SSHes in and runs that
device's own local `cf-agent` against its own local policy file
(`~/.stayturgid/cfengine/stayturgid.cf`); see `just/cfengine.just:cf-run`.
The control node's own `cf-agent`/`cf-promises` binaries are never invoked
against a live device at all — they're used purely for **local policy
authoring**: `just check`'s `cf-promises`-based syntax validation of
`.cf` sources before they're ever pushed out (confirmed via
`device/termux/cfengine/policy/cf-runagent-wrapper.sh`, which is the actual
per-device execution wrapper `cf-serverd`'s `cfruncommand` invokes).

So there's no CFEngine-to-CFEngine network protocol between control node
and fleet to keep compatible here — the real risk of a version mismatch is
**policy-syntax drift**: authoring `.cf` policy against a newer
`cf-promises` that accepts syntax the fleet's older `cf-agent` can't
actually parse/run, which would fail silently or confusingly on-device. The
pin exists to prevent exactly that class of bug, and is a sound design
choice, not an oversight.

## Why a version bump isn't currently actionable

Termux's official package repository (the one every managed device in this
fleet is configured against) tops out at CFEngine `1:3.27.1` — confirmed
live via `apt list -a cfengine` on hd8, no newer version listed. This isn't
a "nobody's packaged it yet" gap so much as a **known upstream portability
blocker**: CFEngine core (from roughly 3.21.x onward) uses `pthread_cancel`,
which Android's Bionic libc doesn't provide, so newer CFEngine core fails
to build under Termux's toolchain at all
(`termux/termux-packages#20803`, tracked upstream as CFEngine's own
`CFE-4401`, with a fix PR submitted against `cfengine/core`). That issue's
activity dates back to at least mid-2024; as of this investigation
(2026-07-28) it still hasn't landed in a released Termux package — the live
`apt list` check above is the actual, current confirmation, not just an
old search result.

Given that, bumping **only** the control node's pinned Homebrew formula to
3.28.0 while the fleet stays capped at 3.27.1 would:

- Do nothing for the fleet (the whole reason the issue exists — `just
cf-run` doesn't touch the control node's binary at all in normal
  operation).
- Actively reintroduce the exact policy-syntax-drift risk the pin was
  created to prevent, for zero fleet-side benefit.

So a real, coordinated version bump isn't safely possible right now — not
because of anything in this repo, but because of an unresolved upstream
Android/Bionic portability bug in CFEngine core itself that Termux's
package build can't currently work around.

## Recommendation

- **No version bump this unit.** Current (3.27.1 control node + fleet,
  matched) is the correct, intentional state given the constraint above —
  not a stale/neglected one.
- **Target, once unblocked:** whatever CFEngine Community release first
  includes a Bionic-compatible fix for `CFE-4401` (currently unreleased).
  When Termux's package repo picks up something newer than 3.27.x, bump
  `packaging/homebrew/cfengine@3.27.1.rb` (rename/bump to match) and the
  fleet's Termux package **together**, in the same change, matching the
  existing "keep them pinned in lockstep" design — never one without the
  other.
- **No action item to track this proactively** — there's no known ETA on
  the upstream fix, and periodically re-checking `apt list -a cfengine` on
  a device (or re-running this investigation) whenever CFEngine policy work
  is already happening is enough; doesn't need its own recurring task.
- `just cf-run` itself needs no changes — it already works correctly
  end-to-end at the current pinned version (this is pre-existing, working
  infrastructure, not something this investigation found broken).

## Verification performed

- `cf-agent --version` / `cf-promises --version` on the control node:
  `3.27.1`.
- Live SSH to hd8: `cf-agent --version` → `3.27.1`; `apt list -a cfengine`
  → only `1:3.27.1` available, confirming the fleet-side ceiling is real
  and current, not stale documentation.
- Read `ansible/roles/control_node/tasks/prereqs.yml`,
  `just/cfengine.just:cf-run`, and
  `device/termux/cfengine/policy/cf-runagent-wrapper.sh` to confirm the
  actual execution architecture (pure SSH + local device execution, no
  control-node-to-fleet CFEngine protocol) rather than assuming one.
