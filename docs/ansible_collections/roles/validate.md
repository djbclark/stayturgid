# stayturgid.fleet.validate

Post-deploy smoke checks over Termux SSH. Complements `just verify` /
`device_tier.py` (deep TAP); does not replace fleet-health launchd probes.

## Playbook wiring

`ansible/playbooks/fleet/validate.yml` imports this role with tag `validate`. Full
`site.yml` runs validate after fleet + post-ui.

```bash
ansible-playbook ansible/playbooks/site.yml --tags validate --limit s24
CHECK=1 ansible-playbook ansible/playbooks/site.yml --tags validate  # skips asserts
```

## What it checks

| Step                               | Source                                            |
| ---------------------------------- | ------------------------------------------------- |
| Repair layer healthy               | `stayturgid_repair_check` (`port=open` or `skip`) |
| Shizuku / sshd / a11y not `FAILED` | Parsed STATUS fields                              |
| A11y profile drift (optional)      | `android_a11y_services` check_mode merge probe    |
| SSH echo                           | `echo termux_ssh_ok`                              |

## Variables (role defaults)

| Var                                | Default | Meaning                                                |
| ---------------------------------- | ------- | ------------------------------------------------------ |
| `stayturgid_validate_a11y_profile` | `true`  | Fail when merge target differs from live list          |
| `stayturgid_validate_a11y_merge`   | `false` | When `true`, merge-restore on drift instead of failing |

Example — heal a11y drift during deploy:

```yaml
stayturgid_validate_a11y_merge: true
```

## Check mode

Repair check and asserts are skipped in check mode. A11y drift probe is skipped
when `ansible_check_mode` is true.

## Not in scope

Watchdog staleness, access-monitor reachability, and full TAP tiers remain in
`device_tier.py` / Mac launchd (`fleet_health_monitor.py`).
