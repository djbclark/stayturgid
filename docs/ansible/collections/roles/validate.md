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

| Step                               | Source                                            |
| ---------------------------------- | ------------------------------------------------- |
| Repair layer healthy               | `stayturgid_repair_check` (`port=open` or `skip`) |
| Shizuku / sshd / a11y not `FAILED` | Parsed STATUS fields                              |
| SSH echo                           | `echo termux_ssh_ok`                              |

## Variables (role defaults)

| Var                    | Default                                       | Meaning                              |
| ---------------------- | --------------------------------------------- | ------------------------------------ |
| `stayturgid_repo_root` | parent of the directory holding `ansible.cfg` | Repo root the repair check runs from |

## Check mode

Repair check and asserts are skipped in check mode.

## Not in scope

Watchdog staleness, access-monitor reachability, and full TAP tiers remain in
`device_tier.py` / Mac launchd (`fleet_health_monitor.py`).
