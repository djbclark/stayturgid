# FIRERPA Native MCP Bridge — Implementation Plan (F1)

**Created:** 2026-07-22

**Status:** Plan accepted for documentation. **Implementation is gated on operator
confirmation of the three open decisions in §4** — no server code is written until
those are settled.

**Priority:** [Priority 7 / F1](outstanding-fix-priorities-2026-07-13.md#priority-7--firerpa-native-mcp-bridge-f1)

**Audience:** Maintainers and junior implementation agents. Read
[`AGENTS.md`](../../../AGENTS.md), [`docs/coding-rules.md`](../../coding-rules.md),
every file in [`.cursor/rules/`](../../../.cursor/rules/), and
[`docs/options.md`](../../options.md) before touching code. This plan does not
override those documents.

## 1. Goal

Build a **Mac-side Python MCP server** that wraps the healing primitives in
[`control/bin/firerpa_heal.py`](../../../control/bin/firerpa_heal.py) as native MCP
tools. Any MCP-capable agent (Claude Code, Claude Desktop, another SDK client) can
then **inspect and repair the fleet over FIRERPA's gRPC channel** without shelling
out to `just firerpa-heal` or parsing text.

The bridge is a **convenience/telemetry layer over an existing, proven heal path**.
It is explicitly **not** a new self-heal control plane (see §8).

## 2. Current state (verified 2026-07-22)

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
- **Known drift bug:** `firerpa_heal.py` `main()` (lines ~191–195) still hardcodes
  the **example** fleet IPs (`100.0.0.11/12/13`), whereas
  `firerpa_health_monitor.py` was updated in `df1e729` to resolve hosts
  dynamically via `ansible-inventory`. So `just firerpa-heal --all` currently
  targets fake IPs. See D3.

## 3. Interpretation of F1

Two readings of "expose repair primitives through the gRPC channel" exist:

- **(A) On-device lamda MCP extension** — use FIRERPA's own `@mcp("tool")`
  decorator so tools run _inside_ the lamda server on the device. This is the
  phrasing in the code-audit doc and older OPTIONS text.
- **(B) Mac-side MCP server wrapping the heal functions** — a standard MCP SDK
  server on the Mac; each tool internally uses `lamda-client` to reach devices
  over gRPC.

**Chosen: (B).** The operator explicitly directed a "Mac-side Python MCP server
that wraps the healing functions … using `uv pip install mcp`." (B) is more
testable, keeps device state minimal, reuses the audited heal code as-is, and does
not require pushing an extension onto every device. (A) remains a possible future
enhancement and is not precluded.

## 4. Open decisions (recommended — **confirm before coding**)

These change the deliverable and the safety surface. Recommendations are marked ★.

### D1 — Tool scope / safety

- ★ **Probes always available; mutating heal tools gated by an env flag.** Expose
  read-only inspection unconditionally; expose `heal_device`, `restart_sshd`,
  `restart_shizuku`, `restart_bootloop` but have them refuse to mutate unless
  `STAYTURGID_ALLOW_FIRERPA_HEAL=1` is set — mirroring the existing UI-automation
  gate (H13, `STAYTURGID_ALLOW_UI_AUTOMATION`). Meets F1's "agents can run fleet
  heal commands" while keeping mutation opt-in.
- Alt 1: probes + full heal, ungated (simplest; matches what `just firerpa-heal`
  already does, but any connected agent can mutate devices with no gate).
- Alt 2: probes only in v1; add mutations in a follow-up.

### D2 — Transport / hosting

- ★ **stdio, local, registered via `.mcp.json`.** Claude Code / MCP clients on
  this Mac spawn the server through the firerpa venv. No network surface, matches
  how agents run here.
- Alt: streamable-HTTP service under launchd, Tailscale-reachable (needed only if
  off-Mac agents must call it; adds a listening port + supervision).

### D3 — Fix the `firerpa_heal.py` fleet drift?

- ★ **Refactor dynamic fleet resolution into a shared helper** (new
  `control/lib/firerpa_fleet.py`, extracted from
  `firerpa_health_monitor.get_fleet`) and use it in `firerpa_heal.py`,
  `firerpa_health_monitor.py`, and the new MCP server. Fixes the
  `just firerpa-heal --all` bug and gives the bridge correct host resolution from
  one source.
- Alt: leave `firerpa_heal.py` untouched; the MCP server resolves hosts on its
  own; log the `firerpa-heal --all` drift as an OPTIONS item.

## 5. Proposed architecture (assumes D1★/D2★/D3★)

```
control/lib/firerpa_fleet.py     # NEW — dynamic {alias: ip} from ansible-inventory
control/lib/firerpa_auth.py      # reuse (certificate_path)
control/bin/firerpa_heal.py      # refactor main() to use firerpa_fleet; heal
                                 #   functions unchanged and import-safe
control/bin/firerpa_mcp.py       # NEW — FastMCP stdio server; imports heal
                                 #   primitives + firerpa_fleet + firerpa_auth
.mcp.json                        # NEW (repo root) — registers the stdio server
just/services.just               # NEW recipe `firerpa-mcp` (thin launcher)
tests/test_firerpa_fleet.py      # NEW — resolver unit tests
tests/test_firerpa_mcp.py        # NEW — tool wiring / gating unit tests (mock Device)
```

The heal functions are already module-level with a `if __name__ == "__main__"`
guard, so importing them from the MCP server is safe. A single shared `Device`
factory (`connect(host, port)` using `certificate_path()`) will live in the MCP
module to avoid duplicating connection/auth logic.

## 6. Tool specification (draft — subject to D1)

| MCP tool           | Params | Returns                              | Class                | Underlying calls                    |
| ------------------ | ------ | ------------------------------------ | -------------------- | ----------------------------------- |
| `list_fleet`       | —      | `[{alias, ip}]`                      | read-only            | `firerpa_fleet.get_fleet()`         |
| `device_status`    | `host` | `{firerpa, sshd, shizuku, bootloop}` | read-only            | `server_info` + `is_*` probes       |
| `heal_device`      | `host` | full result dict                     | **mutating (gated)** | `firerpa_heal.heal_device`          |
| `restart_sshd`     | `host` | `up`/`FAILED`/…                      | **mutating (gated)** | `remove_sshd_down` + `restart_sshd` |
| `restart_shizuku`  | `host` | `repaired`/`port_only`/`FAILED`      | **mutating (gated)** | `restart_shizuku`                   |
| `restart_bootloop` | `host` | `up`/`FAILED`                        | **mutating (gated)** | `restart_bootloop`                  |

- `host` accepts a fleet alias (`s24`/`p7a`/`hd8`) resolved via
  `firerpa_fleet`; unknown aliases return a structured error, never a stack trace.
- Gated tools, when the flag is unset, return a clear "healing disabled — set
  `STAYTURGID_ALLOW_FIRERPA_HEAL=1`" message and perform **no** device mutation.
- Every tool returns structured JSON-serialisable data and maps `lamda` exceptions
  to `{"error": "..."}` rather than raising across the MCP boundary.

## 7. Implementation steps (ordered — for the implementing agent)

1. ✅ Install `mcp` into the firerpa venv (done 2026-07-22).
2. Create `control/lib/firerpa_fleet.py` by extracting `get_fleet()` from
   `firerpa_health_monitor.py`; add `tests/test_firerpa_fleet.py` (mock
   `ansible-inventory` output). Repoint `firerpa_health_monitor.py` at it.
3. Refactor `firerpa_heal.py` `main()` to resolve the fleet via `firerpa_fleet`
   (D3★); keep all heal functions and their signatures unchanged. Verify
   `just firerpa-heal --host s24` still works.
4. Write `control/bin/firerpa_mcp.py` (FastMCP stdio server) implementing §6,
   including the `STAYTURGID_ALLOW_FIRERPA_HEAL` gate (D1★).
5. Add `.mcp.json` registering the server with the venv interpreter; add a thin
   `just firerpa-mcp` launcher recipe.
6. Add `tests/test_firerpa_mcp.py`: tool registration, alias resolution, gate
   behaviour (mutations refused without the flag), error mapping — all with a
   mocked `lamda.client.Device`.
7. Run `just check` and `just test`. Fix lint (ruff) and typing.
8. **Live validation against `s24` only:** MCP handshake / `list_tools`,
   `list_fleet`, `device_status s24` (read-only). Exercise one gated mutation with
   the flag set against `s24` and confirm via `firerpa-health.log`. Announce device
   interaction per convention; no screen lease needed (no glass/UI).
9. Update `docs/options.md` F1 status and add a short note to the FIRERPA section;
   record commands, results, and rollback. Commit + push per protocol.

## 8. Self-heal / deploy coverage (rule compliance)

Per [`.cursor/rules/deploy-self-heal-catastrophic.mdc`](../../../.cursor/rules/deploy-self-heal-catastrophic.mdc)
and [`fleet-health-self-heal.mdc`](../../../.cursor/rules/fleet-health-self-heal.mdc):

- The MCP bridge introduces **no new device desired-state**, so it needs **no new
  `tests/healing_registry.json` entry**. It is a call surface over the existing
  `SSHD-RUNNING` / `SHIZUKU-HEADLESS` / `BOOTLOOP-ALIVE` heals already registered
  for `firerpa_heal.py`.
- It must **not** become a required control plane. The authoritative, unattended
  recovery layers remain Termux boot loop, native-agent co-monitor, Mac launchd
  (`fleet_health_monitor.py` / `firerpa_health_monitor.py`), and `firerpa_heal.py`.
  The bridge is operator/agent-initiated only. Do **not** wire launchd to call it.

## 9. Risks and safety

- **Device mutation over gRPC.** Gated by `STAYTURGID_ALLOW_FIRERPA_HEAL` (D1★).
  Mutations are service-level (`am start`, `am broadcast HEADLESS_START`, removing
  a down-file) — **no** UI automation, so the ScreenControlSession lease does not
  apply.
- **Dirty working tree.** The repo currently carries another agent's uncommitted
  K1 native-agent work (incl. an untracked `agent-release.jks` signing keystore).
  Stage only explicit new files for this work; **never** `git add -A`; never touch
  the other agent's changes. `docs/options.md` and the priorities doc are already
  modified by that agent — coordinate before editing them in step 9.
- **p7a FIRERPA down.** If still down at implementation time, note it in OPTIONS;
  validate the bridge against `s24`.

## 10. Rollback

All additive. To revert: delete `control/bin/firerpa_mcp.py`, `.mcp.json`, the
`firerpa-mcp` recipe, and the new tests; revert the `firerpa_fleet` extraction and
the `firerpa_heal.py`/`firerpa_health_monitor.py` repoints. No device state changes
on rollback.

## 11. Acceptance (maps to F1 completion gate)

- The MCP bridge is implemented and starts under the firerpa venv.
- An MCP client lists the tools and successfully calls the read-only tools against
  live `s24`.
- A gated mutating tool performs and logs a real repair on `s24` when the flag is
  set, and refuses when it is not.
- `just check` and `just test` pass; new unit tests fail against the pre-change
  code and pass after.
- `docs/options.md` reflects F1 status; rollback is documented.
