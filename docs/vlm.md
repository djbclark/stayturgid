# UI-TARS-1.5-7B — local vision gates for Android screenshots

stayturgid uses **UI-TARS-1.5-7B** as an optional Mac-side screenshot verifier during
device QA. Handsets + hierarchy selectors remain primary; VLM is the safety net for
brittle OEM screens.

UI-TARS is a **vendor-neutral Mac sidecar** (Homebrew `llama.cpp` + launchd). Weights
and server logs live outside `~/.config/stayturgid/`. stayturgid fleet config and
`vlm-verify` artifacts stay under `~/.config/stayturgid/`.

Mac install is **Ansible-managed** (`ansible/playbooks/control_node/vlm.yml` via `just vlm-*`).

See [docs/hacking.md § 2.7](hacking.md#27-ui-tars-vision-gates-optional) for dev setup.

---

## Path layout

| Scope                | Location                                     |
| -------------------- | -------------------------------------------- |
| UI-TARS models       | `~/.local/share/ui-tars/models/1.5-7b/`      |
| Server log           | `~/Library/Logs/ui-tars/server.log`          |
| LaunchAgent          | `homebrew.mxcl.ui-tars`                      |
| stayturgid artifacts | `~/.config/stayturgid/artifacts/vlm-verify/` |

Env: `UI_TARS_*` (server), `STAYTURGID_VLM_*` (harness), `QSS_VLM_*` (legacy aliases).

---

## Initial setup

```bash
just configure
just vlm-install
just vlm-service-install
just vlm-check
```

Equivalent Ansible (from repo root):

```bash
ansible-playbook ansible/playbooks/control_node/site.yml --tags vlm-models -e stayturgid_vlm_enabled=true
ansible-playbook ansible/playbooks/control_node/site.yml --tags vlm-service -e stayturgid_vlm_enabled=true
```

Migrate old `~/.config/stayturgid/models/ui-tars-*` (also run automatically on service install):

```bash
python3 control/vlm/ui-tars/vlm_migrate_paths.py
just vlm-service-install
```

---

## Operations

```bash
just vlm-service-status
curl -sf http://127.0.0.1:8081/health && echo OK
just vlm-service-restart
just vlm-service-stop
just vlm-smoke          # stop/start QA (launchd required)
just vlm-server         # manual background (no launchd)
```

`control/lib/vlm_gate.ensure_server()` runs Ansible (`control_node/site.yml --tags agents-ensure` when
the plist exists, `--tags vlm-service` when installing). Every `just deploy` runs
`agents-ensure` for all control-node launchd jobs (stayturgid + UI-TARS).

---

## Make targets

| Target                                     | Purpose                                      |
| ------------------------------------------ | -------------------------------------------- |
| `vlm-install`                              | Ansible: `llama.cpp` + download GGUF (~6 GB) |
| `vlm-service-install`                      | Ansible: launchd agent (persists at login)   |
| `vlm-service-status`                       | health + launchctl summary                   |
| `vlm-check`                                | client smoke test                            |
| `vlm-smoke`                                | bootout/bootstrap QA cycle                   |
| `vlm-server`                               | manual start                                 |
| `vlm-service-stop` / `vlm-service-restart` | launchctl wrappers                           |
| `verify-hd8-google`                        | Example fleet gate                           |

---

## Harness env

| Variable                        | Default                 | Purpose                                                      |
| ------------------------------- | ----------------------- | ------------------------------------------------------------ |
| `STAYTURGID_VLM`                | `0`                     | Enable gates                                                 |
| `STAYTURGID_VLM_STRICT`         | `0`                     | Fail when server down                                        |
| `STAYTURGID_VLM_PORT`           | `8081`                  | Port                                                         |
| `STAYTURGID_VLM_TIMEOUT`        | `900`                   | Inference timeout                                            |
| `STAYTURGID_VLM_MAX_WIDTH`      | `720`                   | Downscale width                                              |
| `STAYTURGID_VLM_CLOUD`          | `auto`                  | Cloud backend: `auto` / `gemini` / `claude` / `both` / `off` |
| `STAYTURGID_VLM_CLOUD_ESCALATE` | `1`                     | Escalate to cloud when local fails / low conf / down         |
| `STAYTURGID_GEMINI_MODEL`       | `gemini-3.1-flash-lite` | Gemini model id                                              |
| `STAYTURGID_CLAUDE_MODEL`       | `claude-sonnet-5`       | Claude model id                                              |

### Cloud API keys (operator-local, never git)

```text
~/.config/stayturgid/gemini.env       # GEMINI_API_KEY=...
~/.config/stayturgid/anthropic.env    # ANTHROPIC_API_KEY=...
```

`chmod 600` both files. Loaded by `control/lib/vlm_cloud.py` (env vars win if already set).

Smoke test:

```bash
python3 control/bin/vlm_check.py --cloud-only
python3 control/bin/vlm_check.py              # local + cloud
```

**Policy:** local UI-TARS first (private/free); cloud Gemini then Claude only on
unavailable / unparseable / low confidence / failed local gate. Not used on the
5-minute fleet-health hot path.

---

## Best practices (Android screenshot gates)

Ported from sibling project principles (`~/src/RevengeQuickSwitcher/VLM.md`) and
adapted for stayturgid fleet QA.

### Design principle

Use VLM for **high-stakes verification**, not every navigation step. Handsets +
a11y / hierarchy remain primary; VLM is the safety net for brittle OEM chrome.

### Capture timing

- Wait for UI to **settle** after taps (**0.8–1.5 s** minimum; longer after
  animations / OEM transitions).
- Capture **after** animations, not mid-transition.
- For “before type / before install confirm” gates, screenshot **immediately
  before** the input event, not after.

### Image quality

- PNG from `adb exec-out screencap -p` (lossless).
- **Downscale** to ~720px width (`STAYTURGID_VLM_MAX_WIDTH`) unless debugging.
- Prefer full-screen context over aggressive crops (settings headers, dialogs).

### Prompt design

- Require **JSON only**: `ok`, `confidence`, `notes` (plus check-specific fields).
- Name **allowed** and **forbidden** UI strings explicitly.
- Keep prompts **single-purpose** (one screenshot, one question).
- Local OpenAI-compatible path: `temperature: 0.1`, modest `max_tokens`.
- Cloud Claude: do **not** send `temperature` on current Sonnet IDs (API rejects it).
- Cloud Gemini “thinking” models may need higher `maxOutputTokens` (default 1024).

### Local-first cloud retry

When cloud is enabled (`STAYTURGID_VLM_CLOUD=auto` + keys present):

1. Run **local** UI-TARS first.
2. On failure / low confidence / local down → **Gemini**, then **Claude**.
3. If both fail, treat it as **device/UI state**, not only model error — clear
   overlays, unlock screen, dismiss system dialogs before spending more cloud.

### Model IDs (July 2026)

| Role                    | Default                     | Notes                                         |
| ----------------------- | --------------------------- | --------------------------------------------- |
| Gemini primary          | `gemini-3.1-flash-lite`     | Known-good on current keys                    |
| Gemini alias            | `gemini-flash-latest`       | Tracks current Flash; may use thinking tokens |
| Claude escalate         | `claude-sonnet-5`           | Second opinion / dense UI                     |
| Claude cheap (optional) | `claude-haiku-4-5-20251001` | Set `STAYTURGID_CLAUDE_MODEL`                 |

Pinned old IDs (`gemini-2.0-flash`, `claude-3-5-haiku-*`, etc.) often **404**.
Override via env when upstream docs recommend a newer stable id.

### Timing budget

| Phase                | Cap                                     |
| -------------------- | --------------------------------------- |
| UI settle / Handsets | seconds                                 |
| Local VLM gate       | `STAYTURGID_VLM_TIMEOUT` (default 900s) |
| Cloud VLM gate       | ~90–120s HTTP                           |

### Cross-project glass

Before UI work on a shared phone (especially **p7a**):

```bash
python3 control/bin/screen_lease.py status
python3 control/bin/screen_lease.py check p7a
```

See [docs/modules/screen-control-lease.md](modules/screen-control-lease.md).

---

## Upstream best-practice sync (RevengeQuickSwitcher)

stayturgid periodically reviews sibling-project VLM notes for reusable practices
(not Discord-specific harness details):

```text
~/src/RevengeQuickSwitcher/VLM.md
```

```bash
just vlm-upstream-check          # now
python3 control/bin/vlm_upstream_check.py --notify
```

| Piece                               | Role                                                         |
| ----------------------------------- | ------------------------------------------------------------ |
| `control/bin/vlm_upstream_check.py` | Hash/diff upstream; write report                             |
| State                               | `~/.config/stayturgid/state/vlm-upstream/`                   |
| Log                                 | `~/.config/stayturgid/logs/vlm-upstream-check.log`           |
| Launchd                             | `com.stayturgid.vlm-upstream-check` (weekly Sun 09:20 local) |

On change: report lists new model ids + watched sections; macOS notification when
run with `--notify` (launchd default). Agents should open the report and port
relevant defaults/docs — do not blindly copy QSS Discord checks.

---

## Repo files

| Path                                     | Role                                         |
| ---------------------------------------- | -------------------------------------------- |
| `ansible/playbooks/control_node/vlm.yml` | Ansible: brew, models, launchd               |
| `control/vlm/ui-tars/`                   | server run scripts, status/stop helpers      |
| `control/lib/vlm_gate.py`                | `VlmGate`, `ensure_server()`, cloud escalate |
| `control/lib/vlm_cloud.py`               | Gemini + Claude backends + key loading       |
| `control/lib/vlm_helpers.py`             | `verify_shot` helpers                        |
| `control/bin/vlm_check.py`               | local + cloud smoke test                     |

Checks: `play_autoupdate_dont`, `aurora_autoupdate_dont`, `no_gms_crash_dialog`,
`play_protect_clear`, `neo_shizuku_installer`, `aurora_shizuku_installer` — see
`CHECK_PROMPTS` in `vlm_gate.py`.
