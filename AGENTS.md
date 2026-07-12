# stayturgid

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on unrooted Android phones across reboots. Fleet: s24, p7a, hd8 managed via Ansible over Tailscale.

## Quick start

```bash
cd ~/stayturgid && git fetch origin --prune && git pull --ff-only origin master
make health && make firerpa-health
```

## Key commands

| Command | Purpose |
|---------|---------|
| `make deploy [HOSTS=s24]` | Full fleet deploy |
| `make deploy-check [HOSTS=s24]` | Dry-run deploy (CHECK=1) |
| `make verify [HOSTS=s24]` | Device tier checks |
| `make verify-drift [HOSTS=s24]` | Ansible-based drift detect |
| `make verify-heal [HOSTS=s24]` | Verify + auto-heal |
| `make health` | Fleet health summary |
| `make firerpa-health` | FIRERPA fleet health |
| `make firerpa-heal --host s24` | Repair via FIRERPA gRPC |
| `make test` | Code-only tests |
| `make deploy-mac` | Mac workstation (brew, launchd) |
| `make ca-status` | SSH CA status/fingerprints |
| `make opencode-web-status` | OpenCode web UI status |
| `make hermes-status` | Hermes worktree status |
| `make vlm-check` | Check VLM server + cloud |

## Environment

- **Mac shell:** `/bin/bash` (dotfiles: `~/.bash_profile`, `~/.bashrc`)
- **FIRERPA venv:** Python 3.12 at `/tmp/lamda-venv` — `source /tmp/lamda-venv/bin/activate`
- **SSH CA:** `~/.ssh/stayturgid_ca` — `make ca-status`
- **OpenCode web:** http://100.113.53.87:4096

## Fleet (s24, p7a, hd8)

| Device | Tailscale | USB Serial | SSH |
|--------|-----------|------------|-----|
| s24 | 100.123.218.30 | RFCX219CHKA | `ssh s24` |
| p7a | 100.65.230.108 | 35261JEHN12374 | `ssh p7a` |
| hd8 | 100.124.55.39 | GN43T503430603PS | `ssh hd8` |

## Conventions

- Use bash (not zsh). Termux has no zsh by default.
- Announce before device interaction: 🚨📱🚨 USING — host — why — ~N min
- Screen control requires `ScreenControlSession` (fail-closed).
- Accessibility writes are merge-only. Never `settings put` the whole list.
- See full policies at `.cursor/rules/*.md`

## Handoff

Full details: `docs/handoff.md` (cold-start, architecture, known issues)
Session history: `docs/history/session-*.md`
