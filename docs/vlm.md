# UI-TARS-1.5-7B — local vision gates for Android screenshots

stayturgid uses **UI-TARS-1.5-7B** as an optional Mac-side screenshot verifier during
device QA. Handsets + hierarchy selectors remain primary; VLM is the safety net for
brittle OEM screens.

UI-TARS is a **vendor-neutral Mac sidecar** (Homebrew `llama.cpp` + launchd). Weights
and server logs live outside `~/.config/stayturgid/`. stayturgid fleet config and
`vlm-verify` artifacts stay under `~/.config/stayturgid/`.

Mac install is **Ansible-managed** (`ansible/playbooks/control_node/vlm.yml` via `make vlm-*`).

See [docs/hacking.md § 2.7](docs/hacking.md#27-ui-tars-vision-gates-optional) for dev setup.

---

## Path layout

| Scope | Location |
|-------|----------|
| UI-TARS models | `~/.local/share/ui-tars/models/1.5-7b/` |
| Server log | `~/Library/Logs/ui-tars/server.log` |
| LaunchAgent | `homebrew.mxcl.ui-tars` |
| stayturgid artifacts | `~/.config/stayturgid/artifacts/vlm-verify/` |

Env: `UI_TARS_*` (server), `STAYTURGID_VLM_*` (harness), `QSS_VLM_*` (legacy aliases).

---

## Initial setup

```bash
make configure
make vlm-install
make vlm-service-install
make vlm-check
```

Equivalent Ansible (from repo root):

```bash
ansible-playbook ansible/playbooks/control_node/site.yml --tags vlm-models -e stayturgid_vlm_enabled=true
ansible-playbook ansible/playbooks/control_node/site.yml --tags vlm-service -e stayturgid_vlm_enabled=true
```

Migrate old `~/.config/stayturgid/models/ui-tars-*` (also run automatically on service install):

```bash
bash control/vlm/ui-tars/vlm_migrate_paths.sh
make vlm-service-install
```

---

## Operations

```bash
make vlm-service-status
curl -sf http://127.0.0.1:8081/health && echo OK
make vlm-service-restart
make vlm-service-stop
make vlm-smoke          # stop/start QA (launchd required)
make vlm-server         # manual background (no launchd)
```

`control/lib/vlm_gate.ensure_server()` runs Ansible (`control_node/site.yml --tags agents-ensure` when
the plist exists, `--tags vlm-service` when installing). Every `make deploy` runs
`agents-ensure` for all control-node launchd jobs (stayturgid + UI-TARS).

---

## Make targets

| Target | Purpose |
|--------|---------|
| `vlm-install` | Ansible: `llama.cpp` + download GGUF (~6 GB) |
| `vlm-service-install` | Ansible: launchd agent (persists at login) |
| `vlm-service-status` | health + launchctl summary |
| `vlm-check` | client smoke test |
| `vlm-smoke` | bootout/bootstrap QA cycle |
| `vlm-server` | manual start |
| `vlm-service-stop` / `vlm-service-restart` | launchctl wrappers |
| `verify-hd8-google` | Example fleet gate |

---

## Harness env

| Variable | Default | Purpose |
|----------|---------|---------|
| `STAYTURGID_VLM` | `0` | Enable gates |
| `STAYTURGID_VLM_STRICT` | `0` | Fail when server down |
| `STAYTURGID_VLM_PORT` | `8081` | Port |
| `STAYTURGID_VLM_TIMEOUT` | `900` | Inference timeout |
| `STAYTURGID_VLM_MAX_WIDTH` | `720` | Downscale width |

---

## Repo files

| Path | Role |
|------|------|
| `ansible/playbooks/control_node/vlm.yml` | Ansible: brew, models, launchd |
| `control/vlm/ui-tars/` | server run scripts, status/stop helpers |
| `control/lib/vlm_gate.py` | `VlmGate`, `ensure_server()` |
| `control/lib/vlm_helpers.py` | `verify_shot` helpers |
| `control/bin/vlm_check.py` | smoke test |

Checks: `play_autoupdate_dont`, `aurora_autoupdate_dont`, `no_gms_crash_dialog`,
`play_protect_clear`, `neo_shizuku_installer`, `aurora_shizuku_installer` — see
`CHECK_PROMPTS` in `vlm_gate.py`.
