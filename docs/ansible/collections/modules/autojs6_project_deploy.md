# autojs6_project_deploy

Deploy the stayturgid AutoJs6 project tree (`project.json`, `main.js`, `lib/`,
`scripts/`) over adb. Used by `stayturgid.fleet.autojs6_watchdog` on Fire OS
(`stayturgid_autojs6_deploy_via_adb: true`) where Termux SSH cannot write
`/sdcard` reliably.

Shared implementation: `plugins/module_utils/autojs6_deploy_util.py` (also
used by `control/tools/autojs6/deploy.py` for USB recovery).

Does **not** install the AutoJs6 APK or start `main.js` — Obtainium + role
handlers own that.

```yaml
- name: Create temporary file for device profile staging
  ansible.builtin.tempfile:
    state: file
    prefix: "stayturgid-{{ inventory_hostname }}-device-"
    suffix: .json
  register: _device_json_tmp
  delegate_to: localhost

- stayturgid.android_common.autojs6_project_deploy:
    device: "{{ lookup('stayturgid.android_common.adb_device', inventory_hostname) }}"
    repo_root: "{{ stayturgid_repo_root }}"
    target: "{{ autojs6_target }}"
    device_json: "{{ _device_json_tmp.path }}"
  delegate_to: localhost
```

(`ansible.builtin.tempfile`, not a fixed `/tmp/stayturgid-<host>-device.json`
path — see tmpfile security audit, 2026-07-21; matches how
`stayturgid.fleet.autojs6_watchdog` itself calls this module.)
