# FIRERPA Native MCP Bridge — Implementation Plan (F1)

**Created:** 2026-07-22 · **Decisions resolved:** 2026-07-23

**Status:** Decisions D1–D3 resolved with the operator (§4). Implementation is
ready to begin. One sub-point remains open for operator veto: the **consent /
notification surface** for remote (Tailscale) callers (§4.1, flagged ⚑).

**Priority:** [Priority 7 / F1](../../archive/plans/outstanding-fix-priorities-2026-07-13.md#priority-7--firerpa-native-mcp-bridge-f1)

**Audience:** Maintainers and junior implementation agents. Read
[`AGENTS.md`](../../../AGENTS.md), [`docs/coding-rules.md`](../../coding-rules.md),
every file in [`docs/rules/`](../../rules/), and
[`docs/options.md`](../../options.md) before touching code. This plan does not
override those documents.

## 1. Goal

Build a **Mac-side Python MCP server** that wraps the healing primitives in
[`control/bin/firerpa_heal.py`](../../../control/bin/firerpa_heal.py) as native MCP
tools, **reachable over Tailscale** so any MCP-capable agent — on this Mac, another
Mac/Linux control node, or (in future) a device managing its peers — can **inspect
and repair the fleet over FIRERPA's gRPC channel** without shelling out to
`just firerpa-heal` or parsing text.

The bridge is a **convenience layer over an existing, proven heal path**. It is
explicitly **not** a new self-heal control plane (see §8).

## 2. Current state (verified 2026-07-22/23)

- **MCP SDK:** `mcp==1.28.1` installed into `~/.venv-stayturgid-firerpa`
  (`uv pip install mcp`). `from mcp.server.fastmcp import FastMCP` imports cleanly.
- **lamda client:** `lamda 10.0` present in the same venv.
- **FIRERPA reachability** (`~/.config/stayturgid/logs/firerpa-health.log`):
  - `s24` (100.123.218.30) — `firerpa=10.0 sshd=up shizuku=up` ✅ (dev/test target)
  - `p7a` (100.65.230.108) — `firerpa=unreachable issues=firerpa_down` ⚠️ real
    anomaly, likely the documented post-reboot UID-2000 bridge relaunch gap;
    tracked separately, **not** a blocker for building the bridge.
  - `hd8` (100.124.55.39) — `firerpa=unreachable` — **expected** (Fire OS SELinux
    blocks FIRERPA; documented no-fix).
- **Reusable primitives** in `firerpa_heal.py` (all take a `lamda.client.Device`):
  - Probes (read-only): `is_sshd_alive`, `is_port_5555_alive`, `is_shizuku_alive`,
    `is_bootloop_alive`.
  - Repairs (device-mutating, service-level over gRPC — no UI/screen automation):
    `remove_sshd_down`, `restart_sshd`, `restart_shizuku`, `restart_bootloop`.
  - Orchestrator: `heal_device(host, port)` — full probe → repair → re-probe,
    returns a result dict.
  - Auth: `control/lib/firerpa_auth.certificate_path()` (fails closed if the PEM
    is absent).
- **Reusable consent/notify precedent** (to mirror for D1):
  - On-device: `device/termux/py/stayturgid_agent_presence.py` — `request_screen()`
    uses `termux-dialog` with `REQUEST_SCREEN_COUNTDOWN_SEC = 10`
    ("Starting in N seconds. Press No to disallow, Yes to start now"), auto-proceeds
    on timeout, and drives a **single coalesced** `termux-notification --id <NID>`
    (stable id updated in place, removed on release).
  - Mac-side: `control/bin/access_monitor.py` `notify()` uses
    `osascript display notification`.
- **Known drift bug:** `firerpa_heal.py` `main()` (lines ~191–195) still hardcodes
  the **example** fleet IPs (`100.0.0.11/12/13`), whereas
  `firerpa_health_monitor.py` (commit `df1e729`) resolves hosts dynamically via
  `ansible-inventory`. So `just firerpa-heal --all` currently targets fake IPs.
  Fixed under D3.

## 3. Interpretation of F1

Two readings of "expose repair primitives through the gRPC channel" exist:

- **(A) On-device lamda MCP extension** — use FIRERPA's own `@mcp("tool")`
  decorator so tools run _inside_ the lamda server on the device.
- **(B) Mac-side MCP server wrapping the heal functions** — a standard MCP SDK
  server on a control node; each tool internally uses `lamda-client` to reach
  devices over gRPC.

**Chosen: (B)** (operator-directed). More testable, reuses the audited heal code
as-is, and requires no on-device extension. (A) remains a possible future
enhancement and is not precluded.

## 4. Decisions (resolved 2026-07-23)

### D1 — Tool scope + consent model → **immediacy + consent-countdown + coalesced notifications**

Probes are always available. Mutating heal tools proceed **by default** (immediacy)
but only after a **countdown the operator can refuse**, mirroring remote screen use.
Activity is surfaced through **coalesced** notifications (one rolling notification
per heal session, not one per action). The earlier env-flag allow-gate is **dropped**
in favour of this model. Full design in §4.1.

### D2 — Transport → **Tailscale-reachable streamable-HTTP service** (+ local stdio)

The server runs as a long-lived **streamable-HTTP** MCP service bound to the
control node's **Tailscale** interface, under launchd, so agents on any tailnet
machine (present and future: multiple Mac/Linux control nodes, or devices managing
peers) can reach it. A **stdio** entry mode is also supported for local Claude Code
dev/registration via `.mcp.json`. Network trust: bind to the Tailscale IP (never
`0.0.0.0`), rely on tailnet ACLs (consistent with the updated FIRERPA trust model —
"standard SSH/Tailscale hygiene"), plus an **optional bearer token** (via
`secretspec`) for defense in depth.

### D3 — `firerpa_heal.py` fleet drift → **fix it (shared resolver)**

Extract dynamic fleet resolution into a new `control/lib/firerpa_fleet.py`
(from `firerpa_health_monitor.get_fleet`) and use it in `firerpa_heal.py`,
`firerpa_health_monitor.py`, and the new MCP server. Fixes the
`just firerpa-heal --all` fake-IP bug and gives all three one source of host truth.
(Per standing operator preference: fix clear adjacent issues while the context is
loaded.)

### 4.1 D1 detail — consent-countdown + coalesced notifications

Reuse the presence conventions rather than invent a new mechanism.

**Consent (pre-mutation), countdown-to-refuse, auto-proceed:**

- New constant `FIRERPA_HEAL_COUNTDOWN_SEC = 10` (mirrors
  `REQUEST_SCREEN_COUNTDOWN_SEC`). Implemented in a new
  `control/lib/firerpa_consent.py`.
- Control-node surface: `osascript` —
  `display dialog "<summary>" buttons {"Refuse","Proceed now"} default button "Proceed now" giving up after N`.
  `giving up after` gives a native countdown: timeout → `gave up:true` → **proceed**;
  "Refuse" → abort the mutation and return a structured `{"status":"refused"}`
  (no device change). This is the Mac-native analog of the on-device
  `termux-dialog` countdown.
- Escape hatches mirroring presence env vars:
  - `STAYTURGID_FIRERPA_HEAL_QUIET=1` — skip the interactive dialog, still send
    notifications, still auto-proceed (scheduled/headless callers).
  - `STAYTURGID_FIRERPA_HEAL_NOCONSENT=1` — debug skip.
  - Default (unset) = interactive countdown.

**Notifications (during + after) — coalesced, never one-per-action:**

- **Target device notification bar:** one stable-id
  `termux-notification --id stayturgid-firerpa-heal` pushed **through the FIRERPA
  gRPC shell** (works even when SSH is down — the reason we use gRPC), updated in
  place across the session, e.g.
  `stayturgid heal s24: sshd✓ 10:02 · shizuku✓ 10:05`. Finalised/removed at session
  end. Direct analog of the presence `NID` pattern; matches "notification bar".
- **Control node (macOS):** exactly **one** summary notification per heal session
  via `osascript display notification`, e.g. `healed s24: sshd, shizuku (2 actions)`
  — emitted at completion, not per action.
- **Coalescing rule:** accumulate per-session actions in the consent/notify helper;
  emit one device-bar notification (updated in place) + one Mac summary. A heal that
  performs three repairs produces **one** device notification and **one** Mac
  notification listing the three actions and their times.

**⚑ Open point for operator veto (surface for remote callers).** A control-node
`osascript` dialog only reaches an operator physically at the MCP-server Mac. Under
D2 the caller may be on another tailnet machine. The fully-correct multi-device
mechanism is **MCP elicitation** (server → client request-for-input), so the prompt
reaches whoever invoked the tool. **Recommendation:** v1 uses control-node
`osascript` consent + coalesced device-bar/Mac notifications (works today, matches
the screen-use analogy); add MCP elicitation as the multi-device evolution once a
remote caller exists. Confirm this phasing, or say if you want elicitation from the
start.

## 5. Architecture

```
control/lib/firerpa_fleet.py     # NEW — dynamic {alias: ip} from ansible-inventory
control/lib/firerpa_consent.py   # NEW — countdown consent (osascript) + coalesced
                                 #   notifications (macOS + device termux-notification
                                 #   via gRPC); env escape hatches
control/lib/firerpa_auth.py      # reuse (certificate_path)
control/bin/firerpa_heal.py      # refactor main() to use firerpa_fleet; heal
                                 #   functions unchanged and import-safe
control/bin/firerpa_mcp.py       # NEW — FastMCP server; transport selectable
                                 #   (stdio | streamable-http); Tailscale-bind + token
                                 #   for http; imports heal primitives + fleet +
                                 #   consent + auth
.mcp.json                        # NEW (repo root) — local stdio registration
just/services.just               # NEW recipes: firerpa-mcp (http service),
                                 #   firerpa-mcp-stdio (local)
<mac launchd>                    # NEW com.stayturgid.firerpa-mcp plist via the Mac
                                 #   provisioning path (deploy-mac / control_node)
tests/test_firerpa_fleet.py      # NEW — resolver unit tests
tests/test_firerpa_consent.py    # NEW — countdown/coalescing/env-hatch unit tests
tests/test_firerpa_mcp.py        # NEW — tool wiring / consent / error-mapping tests
```

The heal functions are module-level with an `if __name__ == "__main__"` guard, so
importing them from the MCP server is safe. A single `connect(host, port)` factory
(using `certificate_path()`) lives in the MCP module to avoid duplicating
connection/auth logic. Consent + notification are centralised in
`firerpa_consent.py` so the coalescing invariant lives in one place.

## 6. Tool specification

| MCP tool           | Params | Returns                              | Class        | Underlying calls                              |
| ------------------ | ------ | ------------------------------------ | ------------ | --------------------------------------------- |
| `list_fleet`       | —      | `[{alias, ip}]`                      | read-only    | `firerpa_fleet.get_fleet()`                   |
| `device_status`    | `host` | `{firerpa, sshd, shizuku, bootloop}` | read-only    | `server_info` + `is_*` probes                 |
| `heal_device`      | `host` | full result dict                     | **mutating** | consent → `firerpa_heal.heal_device`          |
| `restart_sshd`     | `host` | `up`/`FAILED`/… + `{consent}`        | **mutating** | consent → `remove_sshd_down` + `restart_sshd` |
| `restart_shizuku`  | `host` | `repaired`/`port_only`/`FAILED`      | **mutating** | consent → `restart_shizuku`                   |
| `restart_bootloop` | `host` | `up`/`FAILED`                        | **mutating** | consent → `restart_bootloop`                  |

- `host` accepts a fleet alias (`s24`/`p7a`/`hd8`) resolved via `firerpa_fleet`;
  unknown aliases return a structured error, never a stack trace.
- Every mutating tool runs the §4.1 consent countdown first. On refusal it returns
  `{"status":"refused"}` and performs **no** device mutation. On proceed it performs
  the repair, updates the coalesced device-bar + Mac notifications, and returns the
  structured result.
- Every tool returns JSON-serialisable data and maps `lamda` exceptions to
  `{"error": "..."}` rather than raising across the MCP boundary.

## 7. Implementation steps (ordered — for the implementing agent)

1. ✅ Install `mcp` into the firerpa venv (done 2026-07-22).
2. `control/lib/firerpa_fleet.py`: extract `get_fleet()` from
   `firerpa_health_monitor.py`; add `tests/test_firerpa_fleet.py` (mock
   `ansible-inventory` output); repoint the health monitor at it.
3. Refactor `firerpa_heal.py` `main()` to resolve the fleet via `firerpa_fleet`
   (D3); keep all heal functions/signatures unchanged. Verify
   `just firerpa-heal --host s24` still works.
4. `control/lib/firerpa_consent.py`: countdown consent via `osascript`; coalesced
   notifications (macOS summary + device `termux-notification --id` over gRPC);
   env hatches. Unit-test countdown/refuse/coalescing with mocked subprocess + gRPC.
5. `control/bin/firerpa_mcp.py`: FastMCP server implementing §6; transport selector
   (`stdio` | `streamable-http`); Tailscale-IP bind + optional bearer token for http;
   route every mutation through `firerpa_consent`.
6. `.mcp.json` (local stdio) + `just firerpa-mcp` / `firerpa-mcp-stdio` recipes +
   `com.stayturgid.firerpa-mcp` launchd plist via the Mac provisioning path.
7. `tests/test_firerpa_mcp.py`: tool registration, alias resolution, consent
   proceed/refuse, error mapping — mocked `lamda.client.Device`.
8. `just check` + `just test`; fix ruff/typing.
9. **Live validation against `s24` only:** MCP handshake / `list_tools`,
   `list_fleet`, `device_status s24` (read-only); one mutating tool with consent →
   proceed, confirm the repair + coalesced notifications, and a second run → refuse,
   confirm no mutation. Announce device interaction per convention; no screen lease
   needed (no glass/UI).
10. Update `docs/options.md` F1 status + FIRERPA section; record commands, results,
    rollback. Commit + push per protocol.

## 8. Self-heal / deploy coverage (rule compliance)

Per [`docs/rules/deploy-self-heal-catastrophic.md`](../../../docs/rules/deploy-self-heal-catastrophic.md)
and [`fleet-health-self-heal.mdc`](../../../docs/rules/fleet-health-self-heal.md):

- The bridge introduces **no new device desired-state**, so it needs **no new
  `tests/healing_registry.json` entry**. It is a call surface over the existing
  `SSHD-RUNNING` / `SHIZUKU-HEADLESS` / `BOOTLOOP-ALIVE` heals already registered for
  `firerpa_heal.py`.
- It must **not** become a required control plane. The authoritative, unattended
  recovery layers remain Termux boot loop, native-agent co-monitor, Mac launchd
  (`fleet_health_monitor.py` / `firerpa_health_monitor.py`), and `firerpa_heal.py`.
  The bridge is operator/agent-initiated only, and its consent countdown makes it
  interactive by design. Do **not** wire launchd to auto-call the mutating tools.

## 9. Risks and safety

- **Networked device mutation.** The service is reachable across the tailnet and can
  restart device services. Mitigations: Tailscale-IP bind (never `0.0.0.0`), tailnet
  ACLs, optional bearer token, and the §4.1 consent countdown before every mutation.
  Mutations are service-level (`am start`, `am broadcast HEADLESS_START`, removing a
  down-file) — **no** UI automation, so the ScreenControlSession lease does not apply.
- **Consent reachability (⚑).** Control-node `osascript` consent assumes an operator
  at the MCP-server Mac; remote tailnet callers won't see it until MCP elicitation is
  added (§4.1). Until then, remote callers effectively rely on the countdown
  auto-proceed + coalesced notifications.
- **Multi-agent hygiene.** K1 native-agent work landed as `195c5c7`; the tree is
  clean. Still: stage only explicit new files, never `git add -A`, and verify no
  signing keystore (`device/native-agent/agent-release.jks`) is tracked before any
  broad add.
- **p7a FIRERPA down.** If still down at implementation time, note it in OPTIONS;
  validate the bridge against `s24`.

## 10. Rollback

All additive. To revert: delete `control/bin/firerpa_mcp.py`,
`control/lib/firerpa_consent.py`, `.mcp.json`, the launchd plist, the `firerpa-mcp*`
recipes, and the new tests; revert the `firerpa_fleet` extraction and the
`firerpa_heal.py` / `firerpa_health_monitor.py` repoints. No device state changes on
rollback.

## 11. Acceptance (maps to F1 completion gate)

- The MCP bridge starts under the firerpa venv as a Tailscale-reachable
  streamable-HTTP service (and via stdio locally).
- An MCP client lists the tools and successfully calls the read-only tools against
  live `s24`.
- A mutating tool, after the consent countdown proceeds, performs and logs a real
  repair on `s24` and produces exactly one coalesced device-bar notification and one
  Mac summary; a refusal performs no mutation.
- `just check` and `just test` pass; new unit tests fail against the pre-change code
  and pass after.
- `docs/options.md` reflects F1 status; rollback is documented.
