# Handoff — 2026-07-25/26 Shizuku Fire-OS fix · group_vars de-dup · VLM removal

Long session. Three big threads landed and pushed; one large task is queued as
the #1 next priority. This doc is the short version for picking work back up.

## ⭐ #1 PRIORITY next session — peer-start ([#61](https://github.com/djbclark/stayturgid/issues/61))

Build the **external-ADB Shizuku starter into the `stayturgid-agent` APK** so
healthy peers (s24/p7a) can start Shizuku on Fire OS devices **without the
Mac**. Root cause + mechanism are fully proven this session (see #60); this is
the remaining build. Full design sketch, what-to-build-on, and caveats are in
**issue #61**. Start there.

Why it matters: hd8's Shizuku currently only comes up via a **manual** external
ADB starter (Mac or hand-run) — it does **not** survive a reboot on its own.
Issue #61 is what makes Fire-OS Shizuku self-healing and Mac-independent.

## State right now

- **stayturgid `master`**: clean, pushed. This session added, in order:
  `5c7f023`→`ad81eaa` region — the deploy-pipeline fixes from the prior
  handoff, then `606d25b` (shizuku_config tempfile), `7540da3` (Tailscale
  foreground fix), `8cb80d4` (#58 fleet lock), `1e18625` (caddy/registry
  regression fixes), `5606393` (android_apk `clean`), `3c42ecb` (group_vars
  de-dup), `a028544`+`ccfe45a`+`ad81eaa` (VLM removal). All pushed.
- **site-djbclark `master`**: clean, pushed (`35128c6` de-dup, `898467f` VLM
  remnants).
- **djbclark/Shizuku fork**: `e8c314a6` = `release23` published. (`api`
  submodule shows modified content — **pre-existing**, not from this session.)
- **All 564 python tests pass; ruff/markdownlint/ansible-lint/semgrep clean.**
- **Devices:** hd8 (raspite) on release23, Shizuku RUNNING (manual start),
  agent bound. s24 on release23, self-starts fresh on boot. **p7a OFFLINE**
  (dead battery) — still on release21.

## What changed and why (fast version)

### Shizuku Fire-OS headless start — SOLVED ([#60](https://github.com/djbclark/stayturgid/issues/60))

- **Root cause proven (no device root needed):** Fire OS `adbd` drops
  connections whose peer is device-local → Shizuku's loopback self-start
  `EOFException`s. External peers are accepted. Proved via a Mac relay
  (loopback→EOF, relayed→A_AUTH).
- **Packaging fixed:** the earlier `useLegacyPackaging=false` (release21/22) was
  **fleet-wide broken** for fresh server start — the starter points
  `shizuku_server` at the _extracted_ lib dir for `librish.so`, empty when libs
  aren't extracted → `UnsatisfiedLinkError`. Reverted to
  `extractNativeLibs=true` (**release23**) + **clean-reinstall Shizuku on Fire
  OS** (`android_apk` new `clean` param, gated on
  `stayturgid_shizuku_clean_reinstall` in vendor_amazon group_vars).
- **State-machine wedge fixed** (release22): `startDirect()` now resets state
  after retries instead of wedging at STARTING.
- **Validated under real reboot:** s24 self-starts release23 fresh; hd8 starts
  via external ADB, server stays up, agent binds.

### group_vars de-dup — DONE

- Product now owns the taxonomy group_vars; **site-sync generates them** into
  the site (new `product_file` Jinja filter → thin templates; product = single
  source). Site `ansible.cfg` lists `generated/stayturgid/inventory` as a
  lower-precedence inventory source; site group_vars override.
- site-djbclark hand-maintained group_vars: 11 files → **2** (`all.yml`
  site-block + `stayturgid.yml`). Verified: all hosts resolve, site overrides
  win, no warnings.
- **Screen-control tap coords disabled** on s24/p7a/hd8 (operator request) —
  fall back to `null`. Shizuku starts via external ADB, not UI tapping.

### VLM / UI-TARS — ERASED (operator: "too error prone to be useful")

- Removed the whole stack: `control/vlm/`, `vlm_{gate,cloud,helpers}.py`,
  `vlm_*`/`gui_audit`/`verify_hd8_google`/`verify_play_autoupdate` bins + tests,
  ansible vlm deploy + ui-tars launchd, `/vlm/` caddy route, `ui-tars-vlm`
  registry port, VLM docs. Stripped VLM from `fix_hd8_google_stack`,
  `h2_confirm_ui`, `fleet_health_monitor`. Site kept `ANTHROPIC_API_KEY`
  (litellm uses it), dropped `GEMINI_API_KEY`.
- Direction recorded in memory (`feedback_stayturgid_no_screen_control_vlm`):
  **don't reintroduce VLM or coordinate-tap screen automation.**

### Also this session

- `#58` closed — shared `flock` (`control/lib/fleet_deploy_lock.py`) so
  `deploy_fleet.py` and `termux_pkg_nightly.py` can't race.
- Tailscale no longer yanked into the foreground on s24 every ~15 min
  (repair-check false positives; `7540da3`).
- Fixed regressions from an earlier same-day Ollama/LiteLLM caddy commit
  (`1e18625`) — the whole `tests/python/` suite went from ~35 failing to green.

## Open loose ends

1. **p7a offline** (dead battery). When it returns: `just deploy p7a` (or
   bootstrap-apks) to get **release23**, then reboot to flush its stale
   release21 daemon and confirm fresh self-start. It's the only device not yet
   on release23.
2. **hd8 Shizuku is a manual start** — survives until reboot only. #61 fixes
   this. Until then, to bring it up after a drop: restore wireless ADB via USB
   `adb tcpip 5555`, then run the starter over external ADB
   (`LD_LIBRARY_PATH=<libdir> <libdir>/libshizuku.so --apk=<apk>`), then
   `control/tools/native-agent/grant_shizuku.py <hd8> org.stayturgid.agent` +
   restart Shizuku for the agent to bind.
3. Other issues from the prior handoff (#57 deploy speed, #59 collection-wide
   adb timeout) remain open, lower priority than #61.

## ⚠️ Hazards for next session

- **Do NOT `adb reboot` hd8 casually.** It can land raspite in a recovery
  bootloop needing physical recovery-menu wrangling (this session's ordeal —
  no data lost, but it needed the operator at the device). Prefer starting
  Shizuku over external ADB _without_ rebooting. Full notes:
  `memory/project_fireos8_adb_wireless_debugging.md`.
- Wireless ADB is non-persistent on Fire OS across reboot (USB `adb tcpip 5555`
  to restore).
- `site-sync` requires the site registry to have every port the caddy template
  references — optional services (`ollama-llm-api`, `litellm-proxy`) are now
  `{% if ... in ports %}`-guarded; keep new optional routes guarded too.

## Key references

- Issues: **#61 (peer-start, do first)**, #60 (Fire-OS root cause, shipped),
  #45 (K1 residuals), #58 (closed), #57/#59 (open).
- Memory: `feedback_stayturgid_no_screen_control_vlm`,
  `project_fireos8_adb_wireless_debugging` (updated with the full 2026-07-25/26
  detail incl. the reboot hazard).
