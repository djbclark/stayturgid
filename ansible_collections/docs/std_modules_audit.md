# Standard Ansible modules vs stayturgid custom modules

Audit of what the fleet Ansible layer does today and whether well-established
modules could replace custom code.

## Already using Ansible builtins / ansible.posix

| Task | Module | Role |
|------|--------|------|
| SSH public keys | `stayturgid.termux.termux_sshd` | `termux_userland` |
| Package mirror pin | `ansible.builtin.copy` | `stayturgid.termux.termux_userland` |
| Script deploy | `ansible.builtin.copy` | `termux_userland`, `autojs6_watchdog` |
| `termux.properties`, `sshd_config` | `ansible.builtin.lineinfile` | `termux_userland` |
| Device profile JSON | `ansible.builtin.template` | `autojs6_watchdog` |
| Directory trees | `ansible.builtin.file` | `termux_userland` |
| Termux settings reload | `ansible.builtin.command` (`termux-reload-settings`) | handler |

## Custom modules (required — no upstream equivalent)

| Module | Why custom | Std alternative? |
|--------|------------|------------------|
| `stayturgid.termux.termux_pkg` | Termux uses `pkg`/apt with conffile prompts, stuck dpkg, mirror sync races | **No** — `ansible.builtin.apt` targets system apt, not Termux prefix |
| `stayturgid.obtainium.obtainium_app` | Renders Obtainium JSON on device; no Obtainium API | **No** |
| `stayturgid.fdroid.fdroid_repos` | Wraps `fdroidcl` CLI + repo parsing | **No** — no fdroidcl module in ansible.posix |
| `stayturgid.play.play_apps` | apkeep/gplaycli + xapk extract + adb install | **No** — Play has no supported silent-install API on consumer phones |
| `stayturgid.android_common.android_appops` | Idempotent Termux/F-Droid permission grants via adb | **No** |
| `stayturgid.android_common.android_settings` | Idempotent VPN/secure settings via adb | **No** |
| `stayturgid.android_common.shizuku_grant` | Shizuku pm grant + shizuku.json patch | **No** |
| `stayturgid.android_common.android_apk` | adb install with INSTALL_FAILED parsing | **No** |
| `stayturgid.termux.termux_sshd` | authorized_keys + sshd_config + detached restart | **No** |

## Shell tasks — remaining candidates

| Current shell task | Role | Recommendation |
|--------------------|------|----------------|
| `am start fdroidrepos://…` | `fdroid_repos` | Keep in role (UI intent) or thin `android_intent` module |
| Shizuku grant Python script | `fdroid_repos`, `play_store` | **Done** — `shizuku_grant` |
| `adb shell am start` AutoJs6 | `autojs6_watchdog` | Keep — Samsung SecurityException workaround via Termux uid 2000 shell |
| Inline `python3 -c resolve_adb` | _(removed)_ | **Done** — `stayturgid.android_common.adb_device` lookup |
| `cmd appops set … WRITE_SETTINGS` | `termux_userland` | **Done** — `android_appops` |
| `pm grant … POST_NOTIFICATIONS` | `termux_userland` | **Done** — `android_appops` |
| `settings put secure always_on_vpn_*` | `tailscale_vpn` | **Done** — `android_settings` |

## What should NOT move to Ansible

Per HANDOFF architecture research:

1. Runtime watchdog (`stayturgid-repair`, AutoJs6 `main.js`) — devices self-heal
2. Catastrophic Shizuku UI tap — accessibility automation
3. Obtainium in-app confirm flows — use Mac `import_catalog.py` with `ScreenControlSession`

## Distribution best practices (applied in this repo)

1. **One domain per collection** — `termux`, `obtainium`, `fdroid`, `play` install independently.
2. **Shared code in `module_utils`** — `android_common.adb_resolve` dedupes fleet modules.
3. **Lookup plugins for Jinja** — `adb_device` replaces role inline Python.
4. **`meta/runtime.yml` redirects** — `stayturgid.fleet.*` FQCN backward compatibility.
5. **`galaxy.yml` dependencies** — explicit `ansible.posix`, `android_common`.
6. **`ansible-test units` per collection** — module logic tested without devices.
7. **Docs in `ansible_collections/docs/`** — adoption guide separate from fleet HANDOFF.
8. **Site inventory stays out of collections** — `ansible/inventory/` is operator-specific.
9. **Roles ship with their collection** — `stayturgid.termux.termux_userland`, etc.

## Optional next modules (not implemented)

None at this time. `android_apk` and `termux_sshd` are available for direct use
outside the bundled roles when needed.
