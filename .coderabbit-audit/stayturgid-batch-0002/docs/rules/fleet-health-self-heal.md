# Fleet health → self-heal (always-on rule, mandatory)

When you fix a **fleet-health** problem (or any live device failure that
`control/bin/check_fleet_health.py` / `fleet-health.log` would surface), you **must**
also make that failure mode recoverable by existing self-heal paths — not only
by a one-shot manual action in the current session.

## Definition of done for a health fix

A health fix is incomplete until **all** of the following are true:

1. **Symptom cleared** — `python3 control/bin/check_fleet_health.py` is clean (or the
   specific host/`issues=` tag is gone) after the fix.
2. **Self-heal updated** — the same class of failure would be repaired without
   an agent re-running the manual steps, via one or more of:
   - Termux boot loop (`device/termux/boot/` + `stayturgid_*.py`)
   - Native agent heartbeat/repair (`device/native-agent/`, `agent.log` STATUS,
     `CatastrophicRepair`)
   - Mac launchd (`control/bin/fleet_health_monitor.py`, `fire_help_monitor.py`,
     `access_monitor.py`, `adb_reconnect.py`, `control/tools/native-agent/start_agent.py`)
   - Peer/Fire paths (`stayturgid_peer_keepalive.py`, peer bootstrap)
3. **Documented briefly** — note in the commit message (and STATUS/OPTIONS if
   operator-facing) _which_ self-heal path now covers it.

## Checklist (run before declaring fixed)

Ask and answer in the work summary:

| Question                                                              | If no → do this                                                              |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Would Termux's 5-min loop recover this without me?                    | Extend repair / timeouts / Fire `NO_LOCAL_ADB` skips                         |
| Would the native agent's heartbeat/repair cycle recover this?         | Extend `device/native-agent/` HostService / CatastrophicRepair coverage      |
| Would Mac soft-health recover this if the agent/Termux cannot?        | Extend `fleet_health_monitor.py` (or fire-help) with a **rate-limited** heal |
| Did I only run a one-shot (`start_agent.py`, adb taps, manual heals)? | Encode that one-shot into a self-heal path above                             |

## Anti-patterns (do not ship)

- Clearing `agent_stale` only by manually restarting the agent and leaving no
  Mac/Termux restart path.
- Unhanging Fire by killing processes once without timeouts / `NO_LOCAL_ADB`
  guards in the scripts that hung.
- Re-enabling a11y once via Mac UI script without detection/notify coverage
  for the next drop (accessibility itself stays human-gated).
- "Fixed in session" commits that omit self-heal changes when the root cause
  can recur.

## Prefer existing layers

Do **not** invent a fourth control plane. Extend Termux-primary, the native
agent, or Mac launchd. Termux boot loop must **not** call `RunIntentActivity`
(foreground steal); Mac or agent-side paths own process restarts.
