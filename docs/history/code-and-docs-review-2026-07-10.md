# Code and documentation review — stayturgid (2026-07-10)

> **Findings only.** No production code was changed in the commit that adds this
> document. Paths use the **post-reorg** layout (`control/`, `device/`,
> `catalogs/`, `ansible/`, `docs/`) at commit `1d2df1a` (tip of `origin/master`
> when the review started).
>
> Companion historical review (pre-reorg shell era, largely fixed):
> [code-review.md](code-review.md).
>
> **Workspace note:** Produced from the Hermes isolated worktree
> `~/stayturgid-hermes` on branch `hermes/code-docs-review`. Multi-agent git
> source of truth remains `origin/master` on
> `https://github.com/djbclark/stayturgid.git`.

| | |
|--|--|
| **Scope** | Full-repo layout, `control/` + `device/termux/py` Python hot paths, docs tree + relative links, modules vs collections, parked features, new subsystems (ET Mac, Hermes gateway, cloud VLM, screen lease, portrait lock) |
| **Method** | Structural inventory; full reads of focus Python modules; relative-link crawl under `docs/`; comparison to historical [code-review.md](code-review.md); no live device deploy in this pass |
| **Tests** | pytest venv not present in the worktree for this session (`make test-venv` not run). Prior CI shape remains `make test` / `.github/workflows/test.yml` |
| **Severity** | **H** = broken in production paths or agent guidance systematically wrong · **M** = incorrect/harmful in realistic conditions · **L** = quality / completeness |

---

## Executive summary

The **2026-07-10 reorg** (`d950c53` and follow-ons) and subsequent Python migration
fixed nearly all of the 2026-07-06 shell-era High/Medium findings (repair lock
ordering, repair-bridge `pgrep` self-match, battery wallpaper destroy / tier
cascade / `set -e` parse, consent fail-closed, Pixel launcher idle list,
watchdog log trim, adb-reconnect notify spam).

**Open High priorities today:**

1. **Code H1** — Fire / no-local-adb concurrent repair can `NameError` on
   unbound `wifi` in `duplicate_branch()` (no STATUS line under contention).
2. **Docs H1** — ~**48** broken relative links under `docs/` alone (root-style
   `docs/…` targets from files already inside `docs/`).
3. **Docs H2** — OPTIONS **62** / flat playbook shim status is **internally
   contradictory** across handoff, human handoff, architecture, and options.

**Strengths:** modular layout, strong screen-lease + cloud VLM docs, parked
fdroid/play story is consistent, access-monitor debounce pattern is correct,
HD8 Google stack no longer force-pins GMS by default, dual ADB+SSH repair
architecture remains clear.

---

## Code findings

### High

#### H1. `duplicate_branch` — `wifi` unbound on Fire / no-local-adb hosts

`device/termux/py/stayturgid_repair.py` (`duplicate_branch`, ~224–237):

When `privileged_shell_expected()` is False (HD8 / `STAYTURGID_SD` under Termux
home), the branch sets `port, sh, shizuku` but **never assigns `wifi`**, then
interpolates `wifi` into the STATUS string. Concurrent repair (boot loop +
bridge + AutoJs6) takes this path via lock contention → `NameError`, no STATUS
line, non-zero exit instead of advisory `rc=0 (skipped-duplicate)`.

**Fix:** set `wifi = "skip"` in the first branch (mirror `main()` skip path).

**Verified:** source read at review tip; first branch only sets three names.

---

### Medium

#### M1. `fleet_health` age probes use GNU `date -d`

`control/lib/fleet_health.py` (~60–62, ~256–257) — `_age` / similar parse log
timestamps with `date -d "$last"`. On Android toybox/busybox this often fails →
age becomes `0`/`unknown` → stale watchdog/repair can look healthy. Undermines
`fleet_health_monitor` soft alerts and heal.

**Fix:** parse `YYYY-MM-DD HH:MM:SS` in Python after scrape, or log unix epoch.

#### M2. Cross-project screen lease TOCTOU (no lock)

`control/lib/device_screen_lease.py` `acquire` (~319–356) — `find_active_lease`
then `_write_json_atomic` with no `fcntl`/`flock`. Two agents can both see free
and both write; last writer wins. Same-project takeover also always succeeds,
so two stayturgid jobs can clobber each other without `FORCE`.

**Fix:** exclusive lock around check+write; tighten same-project takeover rules.

#### M3. Gemini API key in request URL query string

`control/lib/vlm_cloud.py` — key as `?key=…`. Leaks via proxies, dumps, verbose
HTTP clients. Keys themselves stay outside git (`~/.config/stayturgid/*.env`) —
good.

**Fix:** `x-goog-api-key` (or equivalent) header.

#### M4. Hard-coded `/opt/homebrew/bin/adb` in launchd-facing scripts

`control/bin/adb_reconnect.py`, `control/bin/access_monitor.py` hard-code Apple
Silicon Homebrew adb and ignore `STAYTURGID_ADB` / `stayturgid_device.adb_bin()`.
`fire_peer_help.py` at least honors the env with that default.

**Fix:** use shared `adb_bin()` resolution (as `fleet_health` does).

#### M5. AutoJs6 drawer verify can report OK when still off

`device/termux/py/stayturgid_enable_autojs6.py` (~454–458) — after toggle, if
Handsets path and `want_on` and `sw2 is not None`, returns `"ok"` even when
`sw2[0]` is still False.

**Fix:** only return `"ok"` when `sw2[0] == want_on` (or re-probe settings).

#### M6. On-device presence legacy path points at the same Python file twice

`device/termux/py/stayturgid_screen_control.py` — `PRESENCE_PY` and `PRESENCE_SH`
both reference `stayturgid_agent_presence.py`. Mac `screen_control.py` correctly
falls back to `agent-presence.sh`.

**Fix:** align on-device fallback with Mac, or drop the dead branch.

---

### Low

| ID | Topic | Notes |
|----|--------|--------|
| L1 | Hard-coded swipe coords in `stayturgid_import_catalog.py` | Prefer `wm size` ratios; Handsets path already preferred |
| L2 | AppleScript notify escaping inconsistent | `fleet_health_monitor` escapes; `access_monitor` / `adb_reconnect` do not |
| L3 | `sshd_listening` double-invokes `ss` | Capture once in `stayturgid_repair.py` |
| L4 | Fire-Tools zip download race | Unique temp + atomic replace or flock in `hd8_google_stack.py` |
| L5 | `handsets.Session.__exit__` always stops daemon | Nested UI scripts pay start latency / can kill each other |
| L6 | `et_mac` `StrictHostKeyChecking=accept-new` | OK on trusted Tailscale; pin known_hosts if threat model needs it |
| L7 | `request-screen` timeout fail-open | Intentional; `consent_gate` is fail-closed — document caller choice |
| L8 | `deploy_fleet` Mac re-run only when host limit set | Depends on `site.yml` always importing control_node |
| L9 | Duplicate devices.conf parsers | Consolidate on `stayturgid_device` |

---

### Fixed since historical [code-review.md](code-review.md) (2026-07-06)

| Historical | Status now |
|------------|------------|
| H1 repair functions-before-use | **Fixed** — Python + fcntl lock |
| H2 `pgrep -f repair-bridge` self-match | **Fixed** — pidfile liveness |
| M1 wallpaper destroy | **Fixed** — magic-byte check, restore paths |
| M2 battery tier cascade | **Fixed** — lowest tier only |
| M3 battery `set -e` parse | **Fixed** — JSON + None guard |
| M4 consent timeout fail-open | **Fixed** for `consent_gate`; `request-screen` intentionally open |
| M5 Pixel launcher idle | **Fixed** — nexuslauncher in idle list |
| M8 unbounded watchdog log | **Fixed** — trim in repair |
| M9 adb-reconnect notify spam | **Fixed** — reconnect silent; access_monitor owns alerts |
| Path reorg `mac/` / root `termux/` | **Done** for production trees |
| Secrets in repo | **None found** in focus Python; env under `~/.config/stayturgid/` |

---

### Code: what looks good

- Screen-control fail-closed on inversion + missing presence (Mac and device).
- Battery alarm Python migration is a real improvement over shell.
- `ssh_marked_block` / `et_mac` keep peer-help ForceCommand lines outside fleet key blocks.
- HD8 Google stack default no longer force-downgrades GMS/Play (`STAYTURGID_HD8_PIN_GMS` opt-in).
- Dual-write of repair STATUS for Fire AutoJs6 co-monitor.
- Clear `control/` vs `device/` vs `catalogs/` vs `ansible*` split ([architecture.md](../architecture.md)).

### Suggested code fix order

1. **H1** — one-line Fire concurrent-repair crash.
2. **M1** — soft-health ages (else stale never heals/notifies).
3. **M5** — false AutoJs6 “enabled”.
4. **M2, M3, M4** — lease races, Gemini key header, adb path.
5. L items opportunistically.

---

## Documentation findings

### High

#### H1. Systemic broken relative links under `docs/`

Relative-link crawl from `docs/**/*.md` (review session): **~97 OK, ~48 broken**.
Dominant pattern: files already under `docs/` use **repo-root-style** targets
(`docs/…`, `human/…`, `control/…`), which resolve as `docs/docs/…` etc.

Representative hotspots:

| File | Pattern |
|------|---------|
| `docs/handoff.md` | Many `docs/…`, `human/…`, `control/…` |
| `docs/options.md` | `docs/…`, `human/…` |
| `docs/hacking.md` | `docs/modules/…`; nonexistent collection module paths |
| `docs/other-sites.md` | `docs/…`, `examples/…` |
| `docs/modules/control.md` | `../docs/…` / wrong depth to `control/` |
| `docs/vlm.md` | `docs/hacking.md` → `docs/docs/hacking.md` |

Collection READMEs (especially `stayturgid/fleet`) also point at non-existent
`stayturgid/docs/…` trees; real shared collection docs live under
`ansible_collections/docs/`.

**Fix direction:** from `docs/*` use sibling-relative paths (`hacking.md`,
`modules/…`, `../human/…`, `../control/…`). Add a CI/linkcheck script.

#### H2. Conflicting OPTIONS 62 / flat playbook shim status

| Source | Claims |
|--------|--------|
| `docs/options.md` | OPTIONS **62 closed** 2026-07-10 |
| `docs/architecture.md` | Flat shims **removed** |
| `docs/handoff.md` (parts) | Closed / removed |
| `docs/handoff.md` (other parts) | Still says flat shims remain / “start with OPTIONS 62” |
| `human/HANDOFF-HUMAN.md` | OPTIONS 62 “not executed yet” |

**Ground truth at review tip:** only `ansible/playbooks/site.yml` at the flat
playbooks level; no shim siblings. Agents may restart closed cleanup work.

**Fix:** one cold-start “Next work” block; align human handoff; delete stale bullets.

---

### Medium (docs)

| ID | Topic |
|----|--------|
| M1 | `control.md` / `termux.md` “Full project” links hit `docs/README.md` instead of repo root README |
| M2 | `control/lib/README.md` documents ~4 helpers; missing et_mac, screen_control, lease, fleet_health, VLM, UI stack, hd8_google_stack, ssh_marked_block, … |
| M3 | Collection doc gaps: `android_intent`, `stayturgid_repair_check`, `adb_device` lookup |
| M4 | `docs/hacking.md` repo tree still shows Termux py scripts at `device/termux/*.py` not `device/termux/py/` |
| M5 | `docs/README.md` index gaps: fire-os-google-play, mac-android-ui-automation, history/, human handoff, Hermes/et_mac as first-class rows |
| M6 | Portrait lock under-documented (one handoff sentence; absent from screen-control-lease + cursor rule) |
| M7 | Parked fdroid/play **story is consistent** (good); residual dead collection links from hacking |
| M8 | `control.md` bin inventory incomplete vs live `control/bin/` |

New-feature coverage matrix:

| Feature | Docs quality |
|---------|----------------|
| Screen lease (DSCL) | **Strong** — dedicated module + cursor rule |
| Cloud VLM | **Strong** — `docs/vlm.md` |
| et_mac / phone→Mac ET | **Good but buried** in control module |
| Hermes gateway Ansible | **Good but buried** in control/ansible README |
| Portrait lock | **Thin** |

---

### Low (docs)

- Pre-reorg path instructions largely confined to history + intentional migration tables (good).
- Handoff is large (~45k) and mixes durable policy with dated session notes.
- Incubator index matches tree; parked protocol clear.
- `android_common` README contents table incomplete vs modules on disk.

### Suggested docs fix order

1. **H2** — OPTIONS 62 / shim status single source of truth.
2. **H1** — batch-fix relative links (scripted).
3. **M2 / M5 / M6** — lib README + index + portrait subsection.
4. **M3 / M4** — collection stubs + hacking tree.
5. Opportunistic bin inventory completeness.

---

## Documentation that is already in good shape

- Root [README.md](../../README.md) module map + full-stack path
- [architecture.md](../architecture.md) layout / deploy flow / soft health
- [handoff.md](../handoff.md) agent session policy (modulo H2 contradictions)
- [hacking.md](../hacking.md) clean install walkthrough (modulo link depth)
- Module docs: termux, autojs6, obtainium, fdroid/play parked, control (incl. Hermes/ET), screen-control-lease
- [vlm.md](../vlm.md) local + cloud gates
- ADRs 001–002, incubator parking, `.cursor/rules/*.mdc`, `human/HANDOFF-HUMAN.md`

---

## Repo inventory snapshot (review tip)

| Area | Approx |
|------|--------|
| Python | ~173 files |
| YAML | ~92 |
| Markdown | ~78 |
| `tests/python` | ~42 test modules |
| Top runtimes | Mac `control/`, device Termux + AutoJs6, Ansible collections |

Production layout reminder (for multi-agent coordination):

- Code: `control/`, `device/`, `catalogs/`, `ansible/`, `ansible_collections/`, `docs/`
- AutoJs6: `device/autojs6/` → on device `/sdcard/stayturgid/autojs6/`
- Repair entrypoint: `~/.stayturgid/bin/stayturgid_repair.py` (Python), not the old bash shim

---

## Multi-agent git note (review process)

- Source of truth: **`origin/master`**.
- Hermes agent works in **`~/stayturgid-hermes`** worktree (`hermes/*` branches), not the main `~/stayturgid` checkout, to avoid thrashing concurrent agents.
- Before integrate: `git fetch origin --prune`, rebase/ff onto `origin/master`, never force-push `master`, no secrets in commits.

---

## Out of scope / follow-ups not done here

- Implementing fixes for H/M code items (separate change set + tests).
- Full `make test` / ansible-test / device TAP verify.
- Live fleet health scrape interpretation for the operator’s Mac.
- Rewriting all broken links in the same commit as this findings document
  (intentionally findings-only so both agents can plan fixes without a mixed
  mega-diff).

---

## Changelog of this document

| Date | Note |
|------|------|
| 2026-07-10 | Initial combined code + docs review at `1d2df1a` |
