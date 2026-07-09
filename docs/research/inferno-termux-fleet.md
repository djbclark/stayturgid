# Inferno in Termux — side project (parked)

**Status:** Side project / research only (2026-07-09). **Not** on the stayturgid
hot path. Do not start Phase 0–7 in fleet deploy without an explicit operator
ask.  
**Source plan:** operator upload `Inferno_Termux_Fleet_Plan.md` (archived ideas
below).  
**Audience:** Agents reading [OPTIONS.md](../../OPTIONS.md) or considering
distributed control redesigns.

## One-line verdict

Inferno + Styx + `file2chan` → Shizuku/`rish` is an elegant **namespace UX**
experiment. It does **not** beat stayturgid’s current stack for self-heal, UI
automation, or battery, and should stay out of production until a clear gap
appears that SSH + Ansible + peer ADB + Handsets cannot cover.

## What the plan proposes

Hosted Inferno (`emu`) in Termux on each phone; export synthetic control trees
(`/ctl/permissions/…`, `/ctl/settings/…`) via Styx; mount peers as
`/n/<device>/…`; Limbo handlers call `rish` for elevated `appops` / `settings`.

Constraints match stayturgid: no root, Shizuku elevation, Termux userland.

## How stayturgid already covers the same jobs

| Inferno idea | stayturgid today | Gap? |
|--------------|------------------|------|
| Elevated settings / appops | Ansible `app_privileges`, Mac/Termux harden scripts, `rish` already default-installed | No — Inferno wraps the same `rish` |
| Cross-device control | SSH mesh (`id_ed25519_fleet`), `stayturgid_peer_help` / peer Handsets bootstrap, Mac adb | No — different UX, same reach |
| Unified “fleet as one FS” | Not present | **Yes — UX only** |
| Background always-on control plane | Termux:Boot + sshd; AutoJs6 a11y watchdog (20 min cycle) | Inferno would **add** a third always-on runtime |
| Catastrophic no-shell heal | AutoJs6 accessibility (mandatory) | Inferno **cannot** replace this — needs a live process + shell/`rish` |
| Fast UI hierarchy / taps | Handsets wire + dump fallback | Inferno is not a UI driver |

**Bottom line:** Inferno would mostly re-skin privileged shell ops as path
writes. The hard stayturgid problems (Fire loopback ADB, a11y wipe recovery,
Obtainium/Aurora UI, screen-control consent) sit outside Styx.

## Would integrating it make stayturgid better?

### Worth exploring (side project)

- **Namespace as API:** `echo grant >/n/hd8/ctl/permissions/com.foo` is nicer
  than remembering Ansible tags / script names — good for demos and teaching.
- **Auth story:** Inferno keyring + restricted exports could complement (not
  replace) SSH ForceCommand hardening.
- **Discovery experiments:** Styx mount graph vs static `peers` JSON.

### Not worth folding into core soon

- **Duplicate control plane** next to Ansible + SSH + peer ADB — more failure
  modes, Limbo skill tax, 32/64-bit `emu` build risk on Termux ARM64.
- **Does not shrink AutoJs6 or Handsets** — those solve different layers.
- **Fire OS:** same Shizuku binder timeouts Termux already hits; peer ADB remains
  the Handsets starter. Inferno on hd8 still needs a live elevated helper.
- **ADR boundary:** declarative fleet state stays Ansible; runtime heal stays
  repair + a11y. Inferno fits neither cleanly without becoming “yet another
  orchestrator.”

**Integration worth it?** Only if the operator wants a **Plan 9-style control
UX** as a product goal. For reliability, battery, and deploy simplicity:
**no** for production stayturgid.

## Resource / battery: current vs “move as much as possible to Inferno”

### Current always-on / frequent cost (production)

| Component | When | Relative cost |
|-----------|------|----------------|
| AutoJs6 accessibility | Always (OEM a11y tax) | Medium — required for catastrophic path |
| AutoJs6 `main.js` cycle | Every **20 min** (+ tiny 60s keep-alive) | Low–medium — not continuous CPU |
| Termux `sshd` | After boot / repair | Low idle |
| Shizuku | When started (wireless/ADB) | Low–medium while up |
| Tailscale | Always-on VPN (fleet choice) | Medium (network) |
| Handsets `hs.jar` | **Session-only** (UI scripts) | Spike then stop |
| agent-presence / inversion | UI sessions only | Spike |
| Mac `adb_reconnect` | Mac launchd | Zero on phone |

Phones are daily drivers: stayturgid already avoids keep-awake apps and holds
`svc power stayon` only during agent sessions.

### Inferno-heavy alternative

| Component | When | Relative cost |
|-----------|------|----------------|
| `emu` + JIT + Styx listeners | Always (to be useful as fleet FS) | **Medium–high RAM/CPU** vs sshd |
| `termux-wake-lock` / FGS (plan §6) | Always (Android otherwise kills) | **High battery** — fights deep sleep |
| Limbo → `rish` per write | On each ctl op | Process spawn; fine if rare, bad if chatty |
| Still need AutoJs6 a11y | Always | **No savings** — cannot drop |
| Still need Handsets/SSH for UI & heal | Sessions | **No savings** |

Moving “as much as possible” to Inferno **increases** steady-state drain:
wake locks + a second VM, while the expensive mandatory piece (a11y watchdog)
remains. Replacing Ansible/SSH with Styx does not remove network or elevation
cost — it relocates it into a less battle-tested stack.

**On-demand Inferno** (start `emu` only for a ctl session, like Handsets) would
be kinder on battery but then loses the “always mounted fleet namespace” pitch
and competes poorly with existing SSH one-shots.

### Rough guidance

| Approach | Battery vs today | Capability gain |
|----------|------------------|-----------------|
| Keep current hybrid | Baseline | Production |
| Inferno always-on + wake-lock | **Worse** | Namespace UX |
| Inferno session-only | Similar / slightly worse spikes | Niche ctl demos |
| Drop AutoJs6 “because Inferno” | Looks better on paper | **Breaks** no-shell heal — reject |

## Side-project scope (if picked later)

Do **not** wire into `deploy_fleet.py` / Ansible. Suggested sandbox:

1. One lab device (prefer **s24**): build hosted `emu` (document ARM64/386
   reality — plan’s `OBJTYPE=386` is the first hard gate).
2. Prove `rish -c id` from a Limbo/`os->exec` wrapper (stayturgid already ships
   `~/.stayturgid/bin/rish`).
3. One synthetic file: read/write a single `settings` key via `file2chan`.
4. Optional: mount from a second device over Tailscale — compare to
   `ssh hd8 'rish -c …'`.
5. Stop. Write findings back into this note. No fleet rollout.

## Open questions (from plan — still open)

1. Reliable 64-bit / ARM `emu` on modern Termux?
2. Cleanest Limbo → `rish` bridge?
3. Continuous Inferno + Styx power draw vs idle sshd (measure with
   `termux-battery-status` / Batterystats — do not guess in production)?

## Non-goals

- Replacing AutoJs6, Handsets, Ansible, or SSH mesh
- Always-on Inferno in Termux:Boot
- Inferno as Obtainium/Aurora/UI driver
- Root / custom ROM

## Archived plan summary

Full phased plan (Phase 0 prerequisites → Phase 7 harden) lives in the operator
upload that prompted this note. Core architecture sketch:

```
Termux → Shizuku/rish → Inferno emu
         └── file2chan /ctl/{permissions,settings}/…
         └── styxlisten → peers mount /n/<device>/…
```

Treat that document as inspiration for the sandbox above, not as a stayturgid
roadmap.
