# Session checkpoint — FIRERPA Native MCP Bridge planning (2026-07-23)

**Purpose:** Recoverable handoff for the agent implementing F1.
**OPTIONS:** F1 (Priority 7)
**Plan:** [firerpa-mcp-bridge-plan-2026-07-22.md](../plans/firerpa-mcp-bridge-plan-2026-07-22.md)

## Operator direction

- Build a **Mac-side Python MCP server** wrapping the healing functions in
  `control/bin/firerpa_heal.py` (uses `lamda-client`) as native MCP tools.
- First step done: `uv pip install mcp` into `~/.venv-stayturgid-firerpa`.
- This session was scoped to **documentation only** (plan + decisions); no server
  code was written. Implementation is unblocked but awaits an explicit "go".
- Standing preference (saved to memory `fix-adjacent-issues-in-context`): fix clear
  adjacent issues opportunistically while the context is loaded.

## Session-start checks (2026-07-23)

| Check                       | Result                                                                     |
| --------------------------- | -------------------------------------------------------------------------- |
| Branch / sync               | ✅ on `master`, in sync with `origin/master`                               |
| `just health` (soft/native) | ✅ OK — hd8, p7a, s24 all ok, exit 0                                       |
| `screen_lease status`       | ✅ no active leases                                                        |
| `just firerpa-health`       | ⚠️ exit 1 (silent — logs with `also_print=False`); see FIRERPA state below |
| `mcp` SDK                   | ✅ `mcp==1.28.1` installed in the firerpa venv; `FastMCP` imports          |

**FIRERPA gRPC state** (`~/.config/stayturgid/logs/firerpa-health.log`):

- `s24` (100.123.218.30) — `firerpa=10.0 sshd=up shizuku=up` ✅ (build/test target)
- `p7a` (100.65.230.108) — `firerpa=unreachable` ⚠️ **real anomaly**, likely the
  documented post-reboot UID-2000 bridge relaunch gap. Not yet cleared; log in
  OPTIONS if still down at implementation time.
- `hd8` (100.124.55.39) — `firerpa=unreachable` — **expected** (Fire OS SELinux).

## Decisions resolved with operator (see plan §4)

- **D1 — immediacy + consent-countdown + coalesced notifications.** No env-flag
  gate. Mutating tools proceed by default after a countdown-to-refuse (mirrors
  remote screen use); one rolling coalesced notification per heal session on both
  the device notification bar (`termux-notification --id` over gRPC) and macOS —
  never one-per-action.
- **D2 — Tailscale-reachable streamable-HTTP service** (+ local stdio). Tailscale-IP
  bind, tailnet ACLs, optional bearer token. Rationale: future peer-managing devices
  / additional Mac+Linux control nodes.
- **D3 — fix `firerpa_heal.py` example-IP drift** via a shared
  `control/lib/firerpa_fleet.py` resolver.

## ⚑ Open point (awaiting operator)

Consent surface for **remote tailnet callers**: control-node `osascript` dialog only
reaches an operator at the MCP-server Mac. Correct multi-device mechanism is **MCP
elicitation** (server → client prompt). Recommendation: v1 = `osascript` consent now,
add elicitation when a real remote caller exists. **Confirm phasing or request
elicitation from the start before building the consent path.**

## What was produced this session (documentation only)

- `docs/operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md` — full F1 plan:
  architecture, tool spec, ordered steps, consent/notify design (§4.1), self-heal
  rule compliance, risks, rollback, acceptance.
- Memory: `fix-adjacent-issues-in-context` (+ `MEMORY.md` index).

Commits (all pushed to `origin/master`):

- `2c3638c` docs(f1): initial plan
- `2afa118` docs(f1): finalize decisions D1–D3

## Next steps for the implementing agent

Follow plan §7 (still gated on operator "go" for code):

1. Extract `control/lib/firerpa_fleet.py` from `firerpa_health_monitor.get_fleet`;
   repoint the monitor; add `tests/test_firerpa_fleet.py`.
2. Refactor `firerpa_heal.py` `main()` to use it (D3); keep heal functions unchanged.
3. `control/lib/firerpa_consent.py` — countdown consent + coalesced notifications.
4. `control/bin/firerpa_mcp.py` — FastMCP server, transport selector, Tailscale bind.
5. `.mcp.json` + `just firerpa-mcp*` recipes + `com.stayturgid.firerpa-mcp` launchd.
6. Tests, `just check` + `just test`, live-validate against `s24` only.
7. Update `docs/options.md` F1 status; commit + push.

## Gotchas

- **Repo path:** `~/stayturgid` is a stray 0-byte root-owned file. The real repo is
  **`${OPS_ROOT:-~/ops}/stayturgid`** (session-start doc paths resolve there).
- **Prior dirty tree resolved:** K1 native-agent work landed as `195c5c7`; tree is
  clean. Verify `device/native-agent/agent-release.jks` (signing keystore) never gets
  tracked before any broad `git add`.
- `just firerpa-health` failing silently (exit 1, no console output) is by design
  (`also_print=False`); read `firerpa-health.log` for the real per-host status.
