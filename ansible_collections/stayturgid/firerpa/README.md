# stayturgid.firerpa — FIRERPA/lamda Failsafe Daemon

Deploy [FIRERPA/lamda](https://github.com/firerpa/lamda) v10.0 as an optional
on-device failsafe daemon on stayturgid-managed Android devices.

## What it does

- Runs FIRERPA server on port 65000 (configurable)
- Provides **gRPC API** (160+ methods) as backup control channel
- Optional: built-in SSH, ADB, WebRTC remote desktop
- **Default: disabled** — opt-in per device via inventory

## Quick start

```bash
# Deploy to s24
make firerpa-deploy HOSTS=s24

# Remove from s24
make firerpa-remove HOSTS=s24

# Or via Ansible directly:
ansible-playbook ansible/playbooks/fleet/firerpa.yml -l s24 -e firerpa_enabled=true
```

## Configuration

Set `firerpa_enabled: true` in host_vars or pass `-e firerpa_enabled=true`.

Default config (minimal failsafe — gRPC + SSH only):
```yaml
firerpa_port: 65000
firerpa_sshd_enabled: true
firerpa_adb_enabled: false
firerpa_cron_enabled: false
firerpa_webui_enabled: false
```

## Known limitations

- **SSH auth:** FIRERPA's sshd reads `authorized_keys` from `~/.ssh/` where
  HOME=/ (read-only system partition). Key-based auth requires root or an
  alternative mechanism. The gRPC API is the primary control channel.
- **ADB built-in:** Requires root on v10.0 non-root devices. Use Shizuku's
  adbd on port 5555 as the primary ADB channel.
- **Server binary:** 163 MB (arm64) closed-source native runtime. Pinned to
  v10.0 from stayturgid's fork at https://github.com/djbclark/lamda.

## Related docs

- [FIRERPA Code Audit](../docs/history/firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md)
- [FIRERPA Redundancy Analysis](../docs/history/firerpa-nonroot-redundancy-deepseek-pro-2026-07-12.md)
- [FIRERPA Install Map](../docs/history/firerpa-install-map-2026-07-12.md)
- [FIRERPA Integration Plan](../docs/plans/firerpa-integration-plan.md)
