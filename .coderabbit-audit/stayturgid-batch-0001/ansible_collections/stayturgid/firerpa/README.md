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
# Provision a private service certificate first (default path shown)
test -f ~/.config/stayturgid/firerpa.pem

# Deploy to oneui-device
just firerpa-deploy HOSTS=oneui-device

# Use FIRERPA's certificate-authenticated backup SSH transport
ssh oneui-device-firerpa

# Remove from oneui-device
just firerpa-remove HOSTS=oneui-device

# Or via Ansible directly:
ansible-playbook ansible/playbooks/fleet/firerpa.yml -l oneui-device -e firerpa_enabled=true
```

## Configuration

Set `firerpa_enabled: true` in host_vars or pass `-e firerpa_enabled=true`.

Default config (minimal failsafe — gRPC + SSH only):

```yaml
firerpa_port: 65000
firerpa_certificate_path: ~/.config/stayturgid/firerpa.pem
firerpa_sshd_enabled: true
firerpa_adb_enabled: false
firerpa_cron_enabled: false
firerpa_webui_enabled: false
```

## Known limitations

- **Bootstrapping:** The server archive must run as Android UID 2000 (`shell`).
  After a reboot, the Python Termux supervisor uses localhost ADB. If it is absent,
  authorized Shizuku `rish` restarts adbd on localhost:5555; the supervisor then
  launches through that persistent ADB transport. Direct `rish` background children
  die with their binder session. If neither privileged bridge is usable, USB/wireless
  recovery must restore one before FIRERPA can start. `oneui-device` and `stock-android-device` are validated after
  granting Termux **Allow all the time** in Shizuku.
- **Accessibility coexistence:** Upstream v10.0 calls `getUiAutomation(0)`, suppressing
  ordinary accessibility services. The role hash-guards and patches the bundled DEX to
  use `FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES`, but starts with the signed original
  JAR so FIRERPA's integrity check still passes. It then swaps the patched JAR and
  restarts only the UI helpers. The pinned signed and patched SHA-256 values are
  `b1ac32d902227b7413ff6c867aa42c1630df1de57141e2efbefa0eca8169a67a` and
  `805e39de934d39ebaabe221b4db1464f835cc8ad7753bf3f34f4313569f8f1e1`.
- **SSH auth:** Inbound SSH works as user `shell` on port 65000. The private
  custom service certificate supplies both TLS and SSH trust; the role requires
  it and all Mac gRPC clients fail closed when it is missing.
- **ADB built-in:** Requires root on v10.0 non-root devices. Use Shizuku's
  adbd on port 5555 as the primary ADB channel.
- **Server binary:** 163 MB (arm64) closed-source native runtime. Pinned to
  v10.0 from stayturgid's fork at https://github.com/djbclark/lamda.

## Related docs

- [Standalone non-root justfile and guide](../../../examples/firerpa-nonroot/README.md)
- [FIRERPA Code Audit](../../../docs/research/evaluations/firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md)
- [FIRERPA Redundancy Analysis](../../../docs/research/evaluations/firerpa-nonroot-redundancy-deepseek-pro-2026-07-12.md)
- [FIRERPA Install Map](../../../docs/research/evaluations/firerpa-install-map-2026-07-12.md)
- [FIRERPA Integration Plan](../../../docs/archive/plans/firerpa-integration-plan.md)
