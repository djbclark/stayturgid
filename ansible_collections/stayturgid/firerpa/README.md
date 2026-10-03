# stayturgid.firerpa — FIRERPA/lamda Failsafe Daemon

Deploy [FIRERPA/lamda](https://github.com/firerpa/lamda) v10.9 as an optional
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
- **Accessibility coexistence:** Upstream v10.9 bundles an `Instrumentation` subclass
  whose no-argument `getUiAutomation()` override connects with flags `0`, suppressing
  ordinary accessibility services. The role hash-guards and patches the bundled DEX so
  that override delegates to `getUiAutomation(1)`
  (`FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES`) — one chokepoint covering all four call
  sites, and consistent with upstream's own `Configurator.uiAutomationFlags = 1`. It
  starts with the signed original archive so FIRERPA's integrity check still passes, then
  swaps the patched archive and restarts only the UI helpers. The pinned signed and
  patched `aab.zip` SHA-256 values are
  `74d2f1493025acdb92905d8cf5b5fa75a3978508b440049f81a1dd0eab2c7465` and
  `3be26ac64d6532d1c8635737d4c186c976ea5c1c02e71c17b7207ab0cfbcb510`.
- **SSH auth:** Inbound SSH works as user `shell` on port 65000. The private
  custom service certificate supplies both TLS and SSH trust; the role requires
  it and all Mac gRPC clients fail closed when it is missing.
- **ADB built-in:** Requires root on v10.9 non-root devices. Use Shizuku's
  adbd on port 5555 as the primary ADB channel.
- **ABI:** arm64-v8a only, which covers the whole fleet — s24, p7a, t2e **and hd8**.
  hd8 is worth calling out because an early evaluation doc labelled it `armv7a`;
  that was wrong, the code audit in the same batch corrected it, and hd8 has since
  run this role's arm64 server. No `armeabi-v7a` archive is mirrored or needed.
- **Server binary:** 204 MiB (arm64) closed-source native runtime with an embedded
  Python 3.12. Pinned to v10.9 from stayturgid's fork at
  https://github.com/djbclark/lamda — upstream deletes releases (both v10.0 and v10.2
  are gone), so the fork mirror is the dependable source and the rollback target.

## Related docs

- [Standalone non-root justfile and guide](../../../examples/firerpa-nonroot/README.md)
- [FIRERPA Code Audit](../../../docs/research/evaluations/firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md)
- [FIRERPA Redundancy Analysis](../../../docs/research/evaluations/firerpa-nonroot-redundancy-deepseek-pro-2026-07-12.md)
- [FIRERPA Install Map](../../../docs/research/evaluations/firerpa-install-map-2026-07-12.md)
- [FIRERPA Integration Plan](../../../docs/archive/plans/firerpa-integration-plan.md)
