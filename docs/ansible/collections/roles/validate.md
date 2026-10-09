# stayturgid.fleet.validate

Post-deploy smoke checks over Termux SSH. Complements `just verify` /
`device_tier.py` (deep TAP); does not replace fleet-health launchd probes.

## Playbook wiring

`ansible/playbooks/fleet/validate.yml` imports this role with tag `validate`. Full
`site.yml` runs validate after fleet + post-ui.

```bash
ansible-playbook ansible/playbooks/site.yml --tags validate --limit oneui-device
CHECK=1 ansible-playbook ansible/playbooks/site.yml --tags validate  # skips asserts
```

## What it checks

| Step                                  | Source                                                              |
| ------------------------------------- | ------------------------------------------------------------------- |
| Repair layer healthy                  | `stayturgid_repair_check` (`port=open` or `skip`)                   |
| Shizuku / sshd / a11y not `FAILED`    | Parsed STATUS fields                                                |
| Legacy AutoJs6 a11y probe (warn-only) | `android_a11y_services` probe, only when AutoJs6 is still installed |
| SSH echo                              | `echo termux_ssh_ok`                                                |

## Variables (role defaults)

| Var                                | Default | Meaning                                                                                |
| ---------------------------------- | ------- | -------------------------------------------------------------------------------------- |
| `stayturgid_validate_a11y_profile` | `true`  | Warn (never fail) when AutoJs6 is still installed but its accessibility service is off |

There is no merge or restore variable: the probe is detection only. It is a
leftover from the K1 cutover and does nothing on devices without AutoJs6.

## Check mode

Repair check and asserts are skipped in check mode. The AutoJs6 a11y probe is
skipped when `ansible_check_mode` is true.

## Not in scope

Watchdog staleness, access-monitor reachability, and full TAP tiers remain in
`device_tier.py` / Mac launchd (`fleet_health_monitor.py`).
